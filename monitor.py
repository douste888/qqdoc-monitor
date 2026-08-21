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
    if doc["type"] == "json":
        return json.loads(raw.decode("utf-8"))
    return raw.decode("utf-8", errors="ignore")


def clean_json(x):
    """只保留稳定内容，过滤网页动态字段。"""
    ignore = {
        "updated_at", "update_time", "timestamp", "token", "version",
        "request_id", "server_time", "create_time"
    }
    if isinstance(x, dict):
        return {
            k: clean_json(v)
            for k, v in x.items()
            if k.lower() not in ignore
        }
    if isinstance(x, list):
        return [clean_json(v) for v in x]
    return x


def find_sheet_payload(data):
    found = {}

    def walk(x, path=""):
        if isinstance(x, dict):
            for k, v in x.items():
                p = path + "/" + k
                if k in ("workbook", "related_sheet"):
                    found[p] = clean_json(v)
                walk(v, p)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}/{i}")

    walk(data)
    return found


def main():
    FLAG.unlink(missing_ok=True)
    old = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None
    old_payload = old.get("payload", {}) if old else {}
    payload = {}
    fetched_names = set()

    for doc in DOCS:
        try:
            data = fetch_doc(doc)
            if doc["type"] == "json":
                data = find_sheet_payload(data)
            payload[doc["name"]] = data
            fetched_names.add(doc["name"])
        except Exception as e:
            print("skip", doc["name"], e)
            if doc["name"] in old_payload:
                payload[doc["name"]] = old_payload[doc["name"]]

    if not fetched_names:
        raise RuntimeError("all documents unavailable")

    if old is None:
        SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2))
        print("baseline created")
        return

    changed = []
    for name in fetched_names:
        if old_payload.get(name) != payload.get(name):
            changed.append(name)

    SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2))

    if changed:
        FLAG.write_text("\n".join(sorted(changed)))
        print("document changed:", changed)
    else:
        print("no change")


if __name__ == "__main__":
    main()
