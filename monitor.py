import json
import urllib.request
import hashlib
from pathlib import Path

DOCS = [
    {
        "name": "腾讯文档",
        "type": "json",
        "url": "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DV1BNQkZiamdJaVVI&tab=5b4psn"
    },
    {
        "name": "金山文档",
        "type": "html",
        "url": "https://www.kdocs.cn/l/caTKn3Dbrl3G"
    }
]

SNAPSHOT = Path("snapshot.json")
FLAG = Path("document_changed.flag")


def fetch_doc(doc):
    req = urllib.request.Request(doc["url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()

    if doc["type"] == "json":
        return json.loads(raw.decode("utf-8"))

    return raw.decode("utf-8", errors="ignore")


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
    FLAG.unlink(missing_ok=True)

    payload = {}
    for doc in DOCS:
        data = fetch_doc(doc)
        if doc["type"] == "json":
            data = find_sheet_payload(data)
        payload[doc["name"]] = data

    h = make_hash(payload)
    old = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None

    if old is None:
        SNAPSHOT.write_text(json.dumps({"hash": h, "payload": payload}, ensure_ascii=False, indent=2))
        print("baseline created")
    elif old.get("hash") != h:
        SNAPSHOT.write_text(json.dumps({"hash": h, "payload": payload}, ensure_ascii=False, indent=2))
        FLAG.write_text("document changed")
        print("document changed")
    else:
        print("no change")


if __name__ == "__main__":
    main()
