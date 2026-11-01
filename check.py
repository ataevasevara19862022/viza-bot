import os, re, json, datetime, requests

EMAIL = os.environ["AIS_EMAIL"]
PASSWORD = os.environ["AIS_PASSWORD"]
TG_TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]
DEADLINE = os.environ.get("DEADLINE") or "2099-12-31"
LOCALE = os.environ.get("LOCALE") or "en-uz"
SCHEDULE_ID = os.environ.get("SCHEDULE_ID") or ""
FACILITY_ID = os.environ.get("FACILITY_ID") or ""

STATE_FILE = "state/sent.json"
BASE = f"https://ais.usvisa-info.com/{LOCALE}/niv"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def tg(text):
    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                  data={"chat_id": TG_CHAT, "text": text}, timeout=20)


def csrf(html):
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else ""


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"sent": [], "errors": 0, "started": False}


def save_state(st):
    os.makedirs("state", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(st, f)


def login(s):
    r = s.get(f"{BASE}/users/sign_in", timeout=30)
    token = csrf(r.text)
    if not token:
        raise RuntimeError(f"Kirish sahifasi ochilmadi (status {r.status_code}). "
                           "Sayt GitHub serverini bloklagan bo'lishi mumkin.")
    r = s.post(
        f"{BASE}/users/sign_in",
        data={"utf8": "✓", "user[email]": EMAIL, "user[password]": PASSWORD,
              "policy_confirmed": "1", "commit": "Sign In"},
        headers={"X-CSRF-Token": token, "X-Requested-With":
