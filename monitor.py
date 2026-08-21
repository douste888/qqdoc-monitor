import json
import urllib.request
import hashlib
from pathlib import Path

DOCS = [
    {"name": "现货统计", "type": "json", "url": "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DV1BNQkZiamdJaVVI&tab=5b4psn"},
    {"name": "懒懒单", "type": "html", "url": "https://www.kdocs.cn/l/caTKn3Dbrl3G"},
    {"name": "短线统计", "type": "json", "url": "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DUWRMdkpYY1pIT3J5&tab=0r6mhc"}
]

SNAPSHOT = Path("snapshot.json")
FLAG = Path("document_changed.flag")


def fetch_doc(doc):
    req = urllib.request.Request(doc["url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    return json.loads(raw.decode("utf-8")) if doc["type"] == "json" else raw.decode("utf-8", errors="ignore")


def extract_stable(data):
    found = {}

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("workbook", "related_sheet"):
                    found[k] = v
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data)
    return found


def main():
    FLAG.unlink(missing_ok=True)
    old = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None
    old_payload = old.get("payload", {}) if old else {}
    payload = {}
    fetched = set()

    for doc in DOCS:
        try:
            data = fetch_doc(doc)
            if doc["type"] == "json":
                payload[doc["name"]] = extract_stable(data)
            else:
                payload[doc["name"]] = data
            fetched.add(doc["name"])
        except Exception as e:
            print("skip", doc["name"], e)
            if doc["name"] in old_payload:
                payload[doc["name"]] = old_payload[doc["name"]]

    if not fetched:
        raise RuntimeError("all documents unavailable")

    if old is None:
        SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2))
        print("baseline created")
        return

    changed = [n for n in fetched if old_payload.get(n) != payload.get(n)]
    SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2))

    if changed:
        FLAG.write_text("\n".join(sorted(changed)))
        print("document changed:", changed)
    else:
        print("no change")


if __name__ == "__main__":
    main()
