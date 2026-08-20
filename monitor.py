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


def save_debug(data):
    DEBUG.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def normalize(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return v


def extract_possible_sheet_data(raw):
    """Extract Tencent sheet related payload. The workbook field is compressed and
    may need a decoder, so keep useful intermediate data for analysis."""
    result = {}

    def walk(x, path=""):
        if isinstance(x, dict):
            for k, v in x.items():
                p = path + "/" + str(k)
                if k in ("workbook", "related_sheet", "initialAttributedText"):
                    result[p] = normalize(v)
                walk(v, p)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, path + f"/{i}")

    walk(raw)

    # Current Tencent public API stores sheet content in workbook blobs.
    # Save the discovered structure until a proper decoder is applied.
    if result:
        save_debug(result)

    return result


def stable_hash(data):
    return hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def main():
    raw = fetch()
    cells = extract_possible_sheet_data(raw)

    if not cells:
        print("no sheet payload found")
        return

    current_hash = stable_hash(cells)
    old = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None

    if old is None:
        SNAPSHOT.write_text(json.dumps({"hash": current_hash, "cells": cells}, ensure_ascii=False, indent=2))
        print("baseline created")
        return

    if old.get("hash") != current_hash:
        SNAPSHOT.write_text(json.dumps({"hash": current_hash, "cells": cells}, ensure_ascii=False, indent=2))
        print("sheet payload changed")
    else:
        print("no change")


if __name__ == "__main__":
    main()
