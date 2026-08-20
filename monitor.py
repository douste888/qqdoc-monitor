import json
import urllib.request
import hashlib
from pathlib import Path

URL = "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DV1BNQkZiamdJaVVI&tab=5b4psn"
SNAPSHOT = Path("snapshot.json")
DEBUG = Path("qqdoc_debug.json")


def fetch():
    with urllib.request.urlopen(URL, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def normalize_value(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return v


def find_cell_data(obj):
    """Try to extract real spreadsheet cells and ignore metadata."""
    result = {}

    def walk(x, path=""):
        if isinstance(x, dict):
            # common formats
            if "row" in x and "col" in x:
                value = x.get("value", x.get("text", x.get("v")))
                result[f"{x['row']},{x['col']}"] = normalize_value(value)
                return
            if "r" in x and "c" in x and "v" in x:
                result[f"{x['r']},{x['c']}"] = normalize_value(x["v"])
                return

            for k, v in x.items():
                if k in {
                    "serverTimestamp", "cacheTime", "rev", "revision",
                    "permission", "permissions", "onlineUsers"
                }:
                    continue
                walk(v, path + "/" + str(k))

        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, path + f"/{i}")

    walk(obj)

    if not result:
        DEBUG.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
        return {"parse_status": "no_cells_found"}

    return result


def stable_hash(data):
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def diff_cells(old, new):
    changes = []
    keys = set(old) | set(new)
    for k in sorted(keys):
        if old.get(k) != new.get(k):
            changes.append({"cell": k, "old": old.get(k), "new": new.get(k)})
    return changes


def main():
    raw = fetch()
    cells = find_cell_data(raw)

    if cells.get("parse_status") == "no_cells_found":
        print("no cells parsed")
        return

    current_hash = stable_hash(cells)
    old = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None

    if old is None:
        SNAPSHOT.write_text(json.dumps({"hash": current_hash, "cells": cells}, ensure_ascii=False, indent=2))
        print("baseline created")
        return

    if old.get("hash") != current_hash:
        changes = diff_cells(old.get("cells", {}), cells)
        SNAPSHOT.write_text(json.dumps({"hash": current_hash, "cells": cells}, ensure_ascii=False, indent=2))
        print("cell content changed")
        for c in changes[:20]:
            print(c)
    else:
        print("no cell change")


if __name__ == "__main__":
    main()
