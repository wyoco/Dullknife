import urllib.request
import urllib.parse
import json

SITE_KEY = "6Lfd75osAAAAACKzI8-JUWRGaYV4L3ejVBZMIeyN"
SECRET_KEY = "6Lfd75osAAAAAJhH0u3GhgX7lFBho0cxUEjU_WwN"


def verify_recaptcha(token: str, remote_ip: str = "") -> bool:
    if not token:
        return False
    data = urllib.parse.urlencode({
        "secret": SECRET_KEY,
        "response": token,
        "remoteip": remote_ip,
    }).encode()
    try:
        req = urllib.request.Request(
            "https://www.google.com/recaptcha/api/siteverify",
            data=data,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        return result.get("success", False)
    except Exception as e:
        print(f"[RECAPTCHA ERROR] {e}", flush=True)
        return False
