import os, re, json, datetime, requests

EMAIL = os.environ["AIS_EMAIL"].strip()
PASSWORD = os.environ["AIS_PASSWORD"].strip()
TG_TOKEN = os.environ["TELEGRAM_TOKEN"].strip()
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"].strip()
DEADLINE = (os.environ.get("DEADLINE") or "2099-12-31").strip()
LOCALE = (os.environ.get("LOCALE") or "en-uz").strip()
SCHEDULE_ID = (os.environ.get("SCHEDULE_ID") or "").strip()
FACILITY_ID = (os.environ.get("FACILITY_ID") or "").strip()
APPLICANTS = ["91620788", "91620816"]
STATE_FILE = "state/sent.json"
BASE = "https://ais.usvisa-info.com/" + LOCALE + "/niv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


MANUAL = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"


def tg(text):
    r = requests.post("https://api.telegram.org/bot" + TG_TOKEN + "/sendMessage", data={"chat_id": TG_CHAT, "text": text[:4000]}, timeout=20)
    print("Telegram javobi:", r.status_code, r.text[:300])


def csrf(html):
    m = re.search('name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else ""


def load_state():
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {"sent": [], "errors": 0, "started": False}


def save_state(st):
    os.makedirs("state", exist_ok=True)
    json.dump(st, open(STATE_FILE, "w"))


def login(s):
    r = s.get(BASE + "/users/sign_in", timeout=30)
    token = csrf(r.text)
    if not token:
        raise RuntimeError("Kirish sahifasi ochilmadi (status " + str(r.status_code) + "). Sayt GitHub serverini bloklagan bo'lishi mumkin.")
    form = {"utf8": "✓", "user[email]": EMAIL, "user[password]": PASSWORD, "policy_confirmed": "1", "commit": "Sign In"}
    hdr = {"X-CSRF-Token": token, "X-Requested-With": "XMLHttpRequest", "Accept": "*/*;q=0.5, text/javascript, application/javascript", "Referer": BASE + "/users/sign_in", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    r = s.post(BASE + "/users/sign_in", data=form, headers=hdr, timeout=30)
    if r.status_code != 200 or "Invalid email or password" in r.text:
        raise RuntimeError("Saytga kirib bo'lmadi: email yoki parol noto'g'ri.")


def find_schedule_id(s):
    if SCHEDULE_ID:
        return SCHEDULE_ID
    r = s.get(BASE + "/account", timeout=30)
    m = re.search(r"/schedule/(\d+)/", r.text)
    if not m:
        raise RuntimeError("SCHEDULE_ID topilmadi. Akkauntda to'langan ariza bormi?")
    return m.group(1)


def find_facility_id(html):
    if FACILITY_ID:
        return FACILITY_ID
    m = re.search(r'<option[^>]*value="(\d+)"[^>]*>\s*Tashkent', html, re.I)
    if m:
        return m.group(1)
    sel = re.search('facility_id.*?</select>', html, re.S)
    if sel:
        opts = re.findall(r'<option[^>]*value="(\d+)"', sel.group(0))
        if opts:
            return opts[0]
    for p in [r'facility_id\]"[^>]*value="(\d+)"', r'value="(\d+)"[^>]*facility_id\]"', r'/days/(\d+)\.json', r'facility_id[^0-9<>]{0,40}(\d{2,4})']:
        m = re.search(p, html)
        if m:
            return m.group(1)
    return ""


def facility_debug(html):
    out = []
    for m in re.finditer(r"facility|<select|days/", html, re.I):
        out.append(re.sub(r"\s+", " ", html[max(0, m.start() - 60):m.start() + 120]))
        if len(out) >= 3:
            break
    return " || ".join(out) or "facility so'zi sahifada yo'q"


def page_info(page):
    t = re.search(r"<title>(.*?)</title>", page.text, re.S)
    h = re.search(r"<h[12][^>]*>(.*?)</h[12]>", page.text, re.S)
    title = re.sub(r"\s+", " ", t.group(1)).strip() if t else "-"
    head = re.sub(r"<[^>]+>|\s+", " ", h.group(1)).strip() if h else "-"
    return "Sahifa: " + page.url + " | Sarlavha: " + title + " | " + head


def get_dates():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    login(s)
    sid = find_schedule_id(s)
    appt = BASE + "/schedule/" + sid + "/appointment"
    s.get(appt, timeout=30)
    q = "".join("applicants%5B%5D=" + i + "&" for i in APPLICANTS)
    page = s.get(appt + "?" + q + "confirmed_limit_message=1&commit=Continue", timeout=30)
    fid = find_facility_id(page.text)
    if not fid:
        raise RuntimeError("Konsullik ID topilmadi. " + page_info(page) + "\n\nKOD: " + facility_debug(page.text)[:1500])
    hdr = {"Accept": "application/json, text/javascript, */*; q=0.01", "X-Requested-With": "XMLHttpRequest", "X-CSRF-Token": csrf(page.text), "Referer": appt}
    r = s.get(appt + "/days/" + fid + ".json?appointments[expedite]=false", headers=hdr, timeout=30)
    if "json" not in r.headers.get("Content-Type", ""):
        raise RuntimeError("Sanalar ro'yxati olinmadi (status " + str(r.status_code) + ").")
    return sorted(d["date"] for d in r.json() if "date" in d), appt


def main():
    st = load_state()
    try:
        dates, appt = get_dates()
    except Exception as e:
        st["errors"] = st.get("errors", 0) + 1
        print("XATO:", e)
        if MANUAL or st["errors"] in (1, 5, 20) or str(e) != st.get("last_err"):
            tg("⚠️ Bot xatoga uchradi (" + str(st["errors"]) + "-marta):\n" + str(e))
        st["last_err"] = str(e)
        save_state(st)
        return
    deadline = datetime.date.fromisoformat(DEADLINE)
    good = [d for d in dates if datetime.date.fromisoformat(d) <= deadline]
    new = [d for d in good if d not in st["sent"]]
    print("Bo'sh sanalar:", dates[:5], "| mos keladiganlari:", good[:5])
    if MANUAL or not st.get("started"):
        nearest = dates[0] if dates else "yo'q"
        tg("✅ Bot ishlayapti!\n" + DEADLINE + " gacha bo'lgan joylar kuzatilmoqda.\nHozirgi eng yaqin bo'sh sana: " + nearest)
        st["started"] = True
    if new:
        tg("🔔 YANGI BO'SH JOY CHIQDI!\n\n" + "\n".join("📅 " + d for d in new[:10]) + "\n\nTezroq kiring: " + appt)
    st["sent"] = sorted(set(st["sent"] + new) & set(good))
    st["errors"] = 0
    save_state(st)


if __name__ == "__main__":
    main()
