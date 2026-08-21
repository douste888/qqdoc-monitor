import json
import urllib.request
from pathlib import Path

DOCS = [
    {"name": "现货统计", "type": "json", "url": "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DV1BNQkZiamdJaVVI&tab=5b4psn"},
    {"name": "懒懒单", "type": "html", "url": "https://www.kdocs.cn/l/caTKn3Dbrl3G"},
    {"name": "短线统计", "type": "json", "url": "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DUWRMdkpYY1pIT3J5&tab=0r6mhc"},
]

SNAPSHOT = Path("snapshot.json")
FLAG = Path("document_changed.flag")

FIELD_MAP = {
    "现货统计": {
        1: "时间",
        2: "币种",
        3: "入场点位",
        4: "出本/止损点位",
        5: "出本时盈利率",
    }
}


def fetch_doc(doc):
    req = urllib.request.Request(doc["url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    return json.loads(raw.decode("utf-8")) if doc["type"] == "json" else raw.decode("utf-8", errors="ignore")


def extract_cells(data):
    cells = []

    def walk(x):
        if isinstance(x, dict):
            value = None
            row = x.get("row", x.get("rowIndex"))
            col = x.get("col", x.get("column", x.get("columnIndex")))
            for k in ("text", "value", "content"):
                if isinstance(x.get(k), str):
                    value = x[k]
                    break
            if value is not None:
                cells.append({"row": row, "col": col, "value": value})
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data)
    unique = {(c["row"], c["col"], c["value"]): c for c in cells}
    return list(unique.values())


def normalize(doc, data):
    return {"cells": extract_cells(data)} if doc["type"] == "json" else {"text": data}


def cell_diff(name, old, new):
    old_cells = {(c.get("row"), c.get("col")): c.get("value", "") for c in old.get("cells", [])}
    new_cells = {(c.get("row"), c.get("col")): c.get("value", "") for c in new.get("cells", [])}
    result = []
    for pos in sorted(set(old_cells) | set(new_cells), key=str):
        if old_cells.get(pos) != new_cells.get(pos):
            row, col = pos
            field = FIELD_MAP.get(name, {}).get(col, f"第{col}列")
            result.append(f"{name} 第{row}行 {field}: {old_cells.get(pos,'')} -> {new_cells.get(pos,'')}")
    return result


def main():
    FLAG.unlink(missing_ok=True)
    old = json.loads(SNAPSHOT.read_text("utf-8")) if SNAPSHOT.exists() else None
    old_payload = old.get("payload", {}) if old else {}
    payload = {}
    details = []

    for doc in DOCS:
        try:
            payload[doc["name"]] = normalize(doc, fetch_doc(doc))
        except Exception as e:
            print("skip", doc["name"], e)
            if doc["name"] in old_payload:
                payload[doc["name"]] = old_payload[doc["name"]]

    if old is None:
        SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2), "utf-8")
        print("baseline created")
        return

    for name, data in payload.items():
        if old_payload.get(name) != data:
            details.extend(cell_diff(name, old_payload.get(name, {}), data))

    SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2), "utf-8")

    if details:
        FLAG.write_text("\n".join(details), "utf-8")
        print("document changed")
        print("\n".join(details))
    else:
        print("no change")


if __name__ == "__main__":
    main()
