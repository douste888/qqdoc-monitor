import json
import urllib.request
import hashlib
from pathlib import Path

DOCS = [
    {"name": "现货统计", "type": "json", "url": "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DV1BNQkZiamdJaVVI&tab=5b4psn"},
    {"name": "懒懒单", "type": "html", "url": "https://www.kdocs.cn/l/caTKn3Dbrl3G"},
    {"name": "短线统计", "type": "json", "url": "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DUWRMdkpYY1pIT3J5&tab=0r6mhc"},
]

SNAPSHOT = Path("snapshot.json")
FLAG = Path("document_changed.flag")


def fetch_doc(doc):
    req = urllib.request.Request(doc["url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    return raw.decode("utf-8", errors="ignore")


def clean_content(text):
    # 去除明显动态字段，避免页面刷新导致误报警
    remove_keys = [
        "timestamp",
        "updateTime",
        "serverTime",
    ]
    for key in remove_keys:
        text = text.replace(key, "")
    return text


def make_hash(text):
    text = clean_content(text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize(doc, data):
    return {
        "hash": make_hash(data),
        "length": len(data),
    }


def main():
    FLAG.unlink(missing_ok=True)

    old = json.loads(SNAPSHOT.read_text("utf-8")) if SNAPSHOT.exists() else None
    old_payload = old.get("payload", {}) if old else {}

    payload = {}
    fetched = set()

    for doc in DOCS:
        try:
            payload[doc["name"]] = normalize(doc, fetch_doc(doc))
            fetched.add(doc["name"])
        except Exception as e:
            print("skip", doc["name"], e)
            if doc["name"] in old_payload:
                payload[doc["name"]] = old_payload[doc["name"]]

    if not fetched:
        raise RuntimeError("all documents unavailable")

    if old is None:
        SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2), "utf-8")
        print("baseline created")
        return

    changed = [name for name in fetched if old_payload.get(name) != payload.get(name)]

    SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2), "utf-8")

    if changed:
        FLAG.write_text("\n".join(sorted(changed)), "utf-8")
        print("changed", changed)
    else:
        print("no change")


if __name__ == "__main__":
    main()
