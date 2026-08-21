import json
import urllib.request
from pathlib import Path

DOCS = [
    {
        "name": "现货统计",
        "type": "json",
        "url": "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DV1BNQkZiamdJaVVI&tab=5b4psn",
    },
    {
        "name": "懒懒单",
        "type": "html",
        "url": "https://www.kdocs.cn/l/caTKn3Dbrl3G",
    },
    {
        "name": "短线统计",
        "type": "json",
        "url": "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DUWRMdkpYY1pIT3J5&tab=0r6mhc",
    },
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


def extract_cells(data):
    """只提取真实单元格内容，忽略腾讯文档元数据。"""
    cells = []

    def walk(x):
        if isinstance(x, dict):
            value = None
            row = None
            col = None

            for key in ("text", "value", "content"):
                if key in x and isinstance(x[key], str):
                    value = x[key]
                    break

            for key in ("row", "rowIndex"):
                if key in x:
                    row = x[key]

            for key in ("col", "column", "columnIndex"):
                if key in x:
                    col = x[key]

            if value is not None:
                cells.append({"row": row, "col": col, "value": value})

            for v in x.values():
                walk(v)

        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data)

    unique = {}
    for c in cells:
        key = (c["row"], c["col"], c["value"])
        unique[key] = c

    return sorted(unique.values(), key=lambda x: (str(x["row"]), str(x["col"]), x["value"]))


def normalize(doc, data):
    if doc["type"] == "json":
        return {"cells": extract_cells(data)}
    return {"text": data}


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
        SNAPSHOT.write_text(
            json.dumps({"payload": payload}, ensure_ascii=False, indent=2),
            "utf-8",
        )
        print("baseline created")
        return

    changed = []
    for name in fetched:
        if old_payload.get(name) != payload.get(name):
            changed.append(name)

    SNAPSHOT.write_text(
        json.dumps({"payload": payload}, ensure_ascii=False, indent=2),
        "utf-8",
    )

    if changed:
        FLAG.write_text("\n".join(sorted(changed)), "utf-8")
        print("document changed:", changed)
    else:
        print("no change")


if __name__ == "__main__":
    main()
