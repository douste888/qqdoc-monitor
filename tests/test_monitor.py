import base64
import json
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

import monitor


def tencent_response(workbook: bytes, related_sheet: bytes, **dynamic: object) -> bytes:
    value = {
        "clientVars": {
            "serverTimestamp": dynamic.get("serverTimestamp", 1),
            "traceid": dynamic.get("traceid", "first"),
            "collab_client_vars": {
                "initialAttributedText": {
                    "text": [
                        {
                            "workbook": base64.b64encode(zlib.compress(workbook)).decode(),
                            "related_sheet": base64.b64encode(zlib.compress(related_sheet)).decode(),
                        }
                    ]
                }
            },
        }
    }
    return json.dumps(value).encode()


class ExtractTencentTests(unittest.TestCase):
    def test_ignores_dynamic_response_metadata(self):
        first = tencent_response(b"workbook", b"cells", serverTimestamp=1, traceid="a")
        second = tencent_response(b"workbook", b"cells", serverTimestamp=2, traceid="b")
        self.assertEqual(
            monitor.extract_tencent(first, "", "application/json").fingerprint,
            monitor.extract_tencent(second, "", "application/json").fingerprint,
        )

    def test_detects_sheet_state_change(self):
        first = tencent_response(b"workbook", b"cells")
        second = tencent_response(b"workbook", b"changed cells")
        self.assertNotEqual(
            monitor.extract_tencent(first, "", "application/json").fingerprint,
            monitor.extract_tencent(second, "", "application/json").fingerprint,
        )

    def test_rejects_missing_sheet_state(self):
        with self.assertRaises(monitor.MonitorError):
            monitor.extract_tencent(b"{}", "", "application/json")


class ExtractExportTests(unittest.TestCase):
    def test_rejects_kdocs_login_page(self):
        with self.assertRaises(monitor.MonitorError):
            monitor.extract_export(
                b"<html>login</html>",
                "https://account.kdocs.cn/passport/singlesign",
                "text/html",
            )

    def test_hashes_non_html_export(self):
        data = b"column,value\nname,100\n"
        result = monitor.extract_export(data, "https://example/export", "text/csv")
        self.assertEqual(result.content_bytes, len(data))


class StateTests(unittest.TestCase):
    def test_failure_preserves_previous_snapshot_and_does_not_alert(self):
        document = monitor.Document("doc", "tencent", "https://example")
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text(
                json.dumps(
                    {
                        "version": monitor.SNAPSHOT_VERSION,
                        "documents": {
                            "doc": {
                                "fingerprint": "old",
                                "content_bytes": 10,
                                "extractor": "tencent-sheet-v2",
                            }
                        },
                    }
                ),
                "utf-8",
            )
            with patch.object(monitor, "fetch", side_effect=monitor.MonitorError("offline")):
                with self.assertRaises(monitor.MonitorError):
                    monitor.run([document], snapshot)
            saved = json.loads(snapshot.read_text("utf-8"))
            self.assertEqual(saved["documents"]["doc"]["fingerprint"], "old")

    def test_legacy_snapshot_creates_baseline_without_alert(self):
        document = monitor.Document("doc", "tencent", "https://example")
        body = tencent_response(b"workbook", b"cells")
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text('{"payload":{"doc":{"hash":"legacy"}}}', "utf-8")
            with patch.object(monitor, "fetch", return_value=(body, "https://example", "application/json")):
                result = monitor.run([document], snapshot)
            self.assertEqual(result["changed"], [])
            self.assertEqual(result["initialized"], ["doc"])

    def test_change_is_reported_after_baseline(self):
        document = monitor.Document("doc", "tencent", "https://example")
        first = tencent_response(b"workbook", b"cells")
        second = tencent_response(b"workbook", b"changed")
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            with patch.object(monitor, "fetch", return_value=(first, "https://example", "application/json")):
                monitor.run([document], snapshot)
            with patch.object(monitor, "fetch", return_value=(second, "https://example", "application/json")):
                result = monitor.run([document], snapshot)
            self.assertEqual(result["changed"], ["doc"])

    def test_unstable_candidate_is_not_reported_or_saved(self):
        document = monitor.Document("doc", "tencent", "https://example", optional=True)
        baseline = tencent_response(b"workbook", b"cells")
        candidate = tencent_response(b"workbook", b"candidate")
        different_confirmation = tencent_response(b"workbook", b"different")
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            with patch.object(monitor, "fetch", return_value=(baseline, "https://example", "application/json")):
                monitor.run([document], snapshot)
            before = snapshot.read_text("utf-8")
            with patch.object(
                monitor,
                "fetch",
                side_effect=[
                    (candidate, "https://example", "application/json"),
                    (different_confirmation, "https://example", "application/json"),
                ],
            ):
                result = monitor.run([document], snapshot)
            self.assertEqual(result["changed"], [])
            self.assertIn("doc", result["errors"])
            self.assertEqual(snapshot.read_text("utf-8"), before)


if __name__ == "__main__":
    unittest.main()
