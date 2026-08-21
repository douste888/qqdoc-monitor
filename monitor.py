import json
import urllib.request
import base64
import zlib
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
    if doc["type"] == "json":
        return json.loads(raw.decode("utf-8"))
    return raw.decode("utf-8", errors="ignore")


def try_decode_sheet(value):
    if not isinstance(value, str):
        return None
    try:
        raw = base64.b64decode(value)
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                return zlib.decompress(raw, wbits).decode("utf-8", errors="ignore")
            except Exception:
                pass
    except Exception:
        pass
    return None


def extract_cells(data):
    cells = []

    def parse_text(raw):
        if not isinstance(raw, str):
            return
        try:
            obj = json.loads(raw)
            parse_obj(obj)
        except Exception:
            return

    def parse_obj(obj):
        if isinstance(obj, dict):
            if "text" in obj and isinstance(obj["text"], list):
                for item in obj["text"]:
                    parse_obj(item)
            for k, v in obj.items():
                if k in ("related_sheet", "workbook"):
                    decoded = try_decode_sheet(v)
                    if decoded:
                        parse_text(decoded)
                else:
                    parse_obj(v)
        elif isinstance(obj, list):
            for item in obj:
                parse_obj(item)

        if isinstance(obj, dict):
            row = obj.get("row") or obj.get("row_index") or obj.get("r")
            col = obj.get("col") or obj.get("col_index") or obj.get("c")
            value = obj.get("text") or obj.get("value")
            if row is not None and col is not None and isinstance(value, str):
                cells.append({"row": row, "col": col, "value": value})

    parse_obj(data)
    unique = {(c["row"], c["col"], c["value"]): c for c in cells}
    return sorted(unique.values(), key=lambda x: (str(x["row"]), str(x["col"])))


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
        SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2), "utf-8")
        return

    changed = [n for n in fetched if old_payload.get(n) != payload.get(n)]
    SNAPSHOT.write_text(json.dumps({"payload": payload}, ensure_ascii=False, indent=2), "utf-8")

    if changed:
        FLAG.write_text("\n".join(sorted(changed)), "utf-8")


if __name__ == "__main__":
    main()
