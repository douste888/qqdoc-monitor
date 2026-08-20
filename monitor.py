import json
import urllib.request
import hashlib
from pathlib import Path

URL = "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DV1BNQkZiamdJaVVI&tab=5b4psn"
SNAPSHOT = Path("snapshot.json")

IGNORE_KEYS = {
    "serverTimestamp", "rev", "cacheTime", "userInfo", "permission",
    "permissions", "onlineUsers", "creator", "createdTime", "updatedTime"
}


def fetch():
    with urllib.request.urlopen(URL, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def clean(obj):
    """Remove changing metadata and keep meaningful document data."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if k in IGNORE_KEYS:
                continue
            result[k] = clean(v)
        return result
    if isinstance(obj, list):
        return [clean(x) for x in obj]
    return obj


def stable_hash(data):
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    data = clean(fetch())

    # first successful parse becomes baseline
    current_hash = stable_hash(data)
    old = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None

    if old is None:
        SNAPSHOT.write_text(json.dumps({"hash": current_hash, "data": data}, ensure_ascii=False, indent=2))
        print("baseline created")
        return

    if old.get("hash") != current_hash:
        SNAPSHOT.write_text(json.dumps({"hash": current_hash, "data": data}, ensure_ascii=False, indent=2))
        print("document changed")
    else:
        print("no change")


if __name__ == "__main__":
    main()
