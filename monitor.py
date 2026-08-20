import json
import urllib.request
import hashlib
from pathlib import Path

URL = "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DV1BNQkZiamdJaVVI&tab=5b4psn"
SNAPSHOT = Path("snapshot.json")


def fetch():
    with urllib.request.urlopen(URL, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def find_cell_data(obj):
    """Extract spreadsheet content and ignore Tencent metadata."""
    result = {}

    def walk(x, path=""):
        if isinstance(x, dict):
            # common cell structures
            if "row" in x and "col" in x and ("value" in x or "text" in x):
                result[f"{x['row']},{x['col']}"] = x.get("value", x.get("text"))
            elif "r" in x and "c" in x and "v" in x:
                result[f"{x['r']},{x['c']}"] = x.get("v")
            else:
                for k, v in x.items():
                    walk(v, path + "/" + str(k))
        elif isinstance(x, list):
            for v in x:
                walk(v, path)

    walk(obj)

    # fallback: keep only workbook cell-like data if parser cannot locate cells
    if not result:
        return {"parse_status": "no_cells_found"}

    return result


def stable_hash(data):
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    raw = fetch()
    cells = find_cell_data(raw)

    current_hash = stable_hash(cells)
    old = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None

    if old is None:
        SNAPSHOT.write_text(json.dumps({"hash": current_hash, "cells": cells}, ensure_ascii=False, indent=2))
        print("baseline created")
        return

    if old.get("hash") != current_hash:
        SNAPSHOT.write_text(json.dumps({"hash": current_hash, "cells": cells}, ensure_ascii=False, indent=2))
        print("cell content changed")
    else:
        print("no cell change")


if __name__ == "__main__":
    main()
