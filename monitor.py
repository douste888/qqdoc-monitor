import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path


SNAPSHOT = Path("snapshot.json")
RESULT = Path("monitor-result.json")
SNAPSHOT_VERSION = 2


@dataclass(frozen=True)
class Document:
    name: str
    kind: str
    url: str
    cookie: str | None = None
    optional: bool = False


@dataclass(frozen=True)
class Extracted:
    fingerprint: str
    content_bytes: int
    extractor: str


class MonitorError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(document: Document) -> tuple[bytes, str, str]:
    headers = {
        "Accept": "*/*",
        "Cache-Control": "no-cache",
        "User-Agent": "qqdoc-monitor/2.0 (+https://github.com/douste888/qqdoc-monitor)",
    }
    if document.cookie:
        headers["Cookie"] = document.cookie

    request = urllib.request.Request(document.url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
            content_type = response.headers.get_content_type()
            return data, response.url, content_type
    except (urllib.error.URLError, TimeoutError) as error:
        raise MonitorError(f"request failed: {error}") from error


def extract_tencent(data: bytes, _final_url: str, _content_type: str) -> Extracted:
    try:
        response = json.loads(data.decode("utf-8"))
        attributed = response["clientVars"]["collab_client_vars"]["initialAttributedText"]
        records = attributed["text"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise MonitorError("Tencent response does not contain initial sheet state") from error

    if not isinstance(records, list) or not records:
        raise MonitorError("Tencent sheet state is empty")

    parts: list[dict[str, object]] = []
    total_bytes = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        for field in ("workbook", "related_sheet"):
            encoded = record.get(field)
            if not isinstance(encoded, str) or not encoded:
                continue
            try:
                compressed = base64.b64decode(encoded, validate=True)
                decoded = zlib.decompress(compressed)
            except (ValueError, zlib.error) as error:
                raise MonitorError(f"invalid Tencent {field} payload") from error
            if not decoded:
                raise MonitorError(f"empty Tencent {field} payload")
            total_bytes += len(decoded)
            parts.append(
                {
                    "field": field,
                    "index": index,
                    "length": len(decoded),
                    "sha256": sha256(decoded),
                }
            )

    fields = {part["field"] for part in parts}
    if fields != {"workbook", "related_sheet"}:
        raise MonitorError("Tencent response is missing workbook or related_sheet")

    canonical = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return Extracted(sha256(canonical.encode("utf-8")), total_bytes, "tencent-sheet-v2")


def extract_export(data: bytes, final_url: str, content_type: str) -> Extracted:
    host = urllib.parse.urlparse(final_url).hostname or ""
    if host == "account.kdocs.cn" or "passport" in final_url:
        raise MonitorError("KDocs requires sign-in; received the account page")
    if content_type in {"text/html", "application/xhtml+xml"}:
        raise MonitorError("KDocs URL returned an HTML page instead of exported document data")
    if len(data) < 16:
        raise MonitorError("exported document data is empty")
    return Extracted(sha256(data), len(data), "raw-export-v1")


EXTRACTORS = {
    "tencent": extract_tencent,
    "export": extract_export,
}


def configured_documents() -> list[Document]:
    documents = [
        Document(
            "现货统计",
            "tencent",
            "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DV1BNQkZiamdJaVVI&tab=5b4psn",
        ),
        Document(
            "短线统计",
            "tencent",
            "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DUWRMdkpYY1pIT3J5&tab=0r6mhc",
        ),
    ]

    kdocs_url = os.environ.get("KDOCS_EXPORT_URL", "").strip()
    if kdocs_url:
        documents.append(
            Document(
                "懒懒单",
                "export",
                kdocs_url,
                cookie=os.environ.get("KDOCS_COOKIE") or None,
                optional=True,
            )
        )
    return documents


def load_snapshot(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"version": SNAPSHOT_VERSION, "documents": {}}
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": SNAPSHOT_VERSION, "documents": {}}
    if value.get("version") != SNAPSHOT_VERSION or not isinstance(value.get("documents"), dict):
        return {"version": SNAPSHOT_VERSION, "documents": {}}
    return value


def write_json_if_changed(path: Path, value: dict[str, object]) -> None:
    serialized = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not path.exists() or path.read_text("utf-8") != serialized:
        path.write_text(serialized, "utf-8")


def write_outputs(changed: list[str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"has_changes={'true' if changed else 'false'}\n")
        output.write("changed<<MONITOR_EOF\n")
        output.write("\n".join(changed) + "\n")
        output.write("MONITOR_EOF\n")


def run(documents: list[Document], snapshot_path: Path = SNAPSHOT) -> dict[str, object]:
    snapshot = load_snapshot(snapshot_path)
    old_documents = snapshot["documents"]
    assert isinstance(old_documents, dict)
    new_documents = dict(old_documents)

    changed: list[str] = []
    initialized: list[str] = []
    errors: dict[str, str] = {}

    for document in documents:
        try:
            data, final_url, content_type = fetch(document)
            extracted = EXTRACTORS[document.kind](data, final_url, content_type)
        except MonitorError as error:
            errors[document.name] = str(error)
            print(f"ERROR {document.name}: {error}", file=sys.stderr)
            continue

        current = asdict(extracted)
        previous = old_documents.get(document.name)
        if isinstance(previous, dict) and previous.get("extractor") == extracted.extractor:
            if previous.get("fingerprint") != extracted.fingerprint:
                try:
                    confirm_data, confirm_url, confirm_type = fetch(document)
                    confirmed = EXTRACTORS[document.kind](confirm_data, confirm_url, confirm_type)
                except MonitorError as error:
                    errors[document.name] = f"change confirmation failed: {error}"
                    print(f"ERROR {document.name}: {errors[document.name]}", file=sys.stderr)
                    continue
                if confirmed.fingerprint != extracted.fingerprint:
                    errors[document.name] = "source was unstable during change confirmation"
                    print(f"ERROR {document.name}: {errors[document.name]}", file=sys.stderr)
                    continue
                changed.append(document.name)
        else:
            initialized.append(document.name)
        new_documents[document.name] = current
        print(
            f"OK {document.name}: extractor={extracted.extractor} "
            f"bytes={extracted.content_bytes} fingerprint={extracted.fingerprint[:12]}"
        )

    required_names = {document.name for document in documents if not document.optional}
    successful_required = required_names - errors.keys()
    if required_names and not successful_required:
        raise MonitorError("all required documents failed")

    new_snapshot: dict[str, object] = {
        "version": SNAPSHOT_VERSION,
        "documents": new_documents,
    }
    write_json_if_changed(snapshot_path, new_snapshot)

    result: dict[str, object] = {
        "changed": changed,
        "initialized": initialized,
        "errors": errors,
    }
    write_json_if_changed(RESULT, result)
    write_outputs(changed)
    return result


def main() -> int:
    try:
        result = run(configured_documents())
    except MonitorError as error:
        print(f"FATAL: {error}", file=sys.stderr)
        return 2

    changed = result["changed"]
    errors = result["errors"]
    if changed:
        print("CHANGED:", ", ".join(changed))
    else:
        print("NO CHANGE")
    if errors:
        print("Some optional or individual sources were unavailable; their snapshots were preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
