import json
import urllib.request
import hashlib
import re
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
        return r.read().decode("utf-8", errors="ignore")


def clean_text(text):
    # remove scripts/styles and common dynamic values
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\\u[0-9a-fA-F]{4}", "", text)
    for key in ["timestamp", "updateTime", "serverTime", "requestId", "traceId"]:
        text = re.sub(key + r"[^,}\s]*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def make_hash(text):
    return hashlib.sha256(clean_text(text).encode("utf-8")).hexdigest()


def main():
    FLAG.unlink(missing_ok=True)

    old = json.loads(SNAPSHOT.read_text("utf-8")) if SNAPSHOT.exists() else None
    old_payload = old.get("payload", {}) if old else {}

    payload = {}
    fetched = []

    for doc in DOCS:
        try:
            raw = fetch_doc(doc)
            payload[doc["name"]] = {
                "hash": make_hash(raw),
                "length": len(clean_text(raw))
            }
            fetched.append(doc["name"])
        except Exception as e:
            print("skip", doc["name"], e)

    if not fetched:
        raise RuntimeError("all documents unavailable")

    if old is None:
        SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2), "utf-8")
        return

    changed = [x for x in fetched if old_payload.get(x) != payload.get(x)]

    SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2), "utf-8")

    if changed:
        FLAG.write_text("\n".join(changed), "utf-8")
        print("changed", changed)
    else:
        print("no change")


if __name__ == "__main__":
    main()
