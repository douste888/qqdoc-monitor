import json
import urllib.request
import hashlib
from pathlib import Path

URL = "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DV1BNQkZiamdJaVVI&tab=5b4psn"
SNAPSHOT = Path("snapshot.json")


def fetch():
    with urllib.request.urlopen(URL, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def find_sheet_payload(data):
    found = {}

    def walk(x, path=""):
        if isinstance(x, dict):
            for k, v in x.items():
                p = path + "/" + k
                if k in ("workbook", "related_sheet"):
                    found[p] = v
                walk(v, p)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}/{i}")

    walk(data)
    return found


def make_hash(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main():
    payload = find_sheet_payload(fetch())
    if not payload:
        print("no payload")
        return

    h = make_hash(payload)
    old = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None

    if old is None:
        SNAPSHOT.write_text(json.dumps({"hash": h, "payload": payload}, ensure_ascii=False, indent=2))
        print("baseline created")
    elif old.get("hash") != h:
        SNAPSHOT.write_text(json.dumps({"hash": h, "payload": payload}, ensure_ascii=False, indent=2))
        print("document changed")
    else:
        print("no change")


if __name__ == "__main__":
    main()
