"""Offline tests for durable delivery receipt records and backwards compatibility."""
import tempfile
import unittest
from pathlib import Path
from orchestration.report_outbox import ReportOutbox

class AuditedDeliveryTests(unittest.TestCase):
    def test_receipt_survives_restart_and_is_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.sqlite"
            box = ReportOutbox(path)
            digest = box.publish("owner", "event", "task", {"status": "complete"}, ["chat", "work"])
            with self.assertRaises(ValueError):
                box.acknowledge_verified("owner", "chat", "event", digest, "")
            with self.assertRaises(ValueError):
                box.acknowledge_verified("owner", "chat", "event", "wrong", "external-ref")
            self.assertEqual(len(box.pending("owner", "chat")), 1)
            box.acknowledge_verified("owner", "chat", "event", digest, "verified-external-ref")
            box.acknowledge_verified("owner", "chat", "event", digest, "verified-external-ref")
            with self.assertRaises(ValueError):
                box.acknowledge_verified("owner", "chat", "event", digest, "conflicting-ref")
            self.assertEqual(box.pending("owner", "chat"), [])
            self.assertEqual(len(box.pending("owner", "work")), 1)
            self.assertIsNone(box.delivery_receipt("other", "chat", "event"))
            box.close()
            box = ReportOutbox(path)
            self.assertEqual(box.delivery_receipt("owner", "chat", "event"),
                             {"sha256": digest, "receipt_ref": "verified-external-ref"})
            box.close()

    def test_legacy_acknowledge_still_works(self):
        with tempfile.TemporaryDirectory() as directory:
            box = ReportOutbox(Path(directory) / "outbox.sqlite")
            digest = box.publish("owner", "event", "task", {"ok": True}, ["chat"])
            box.acknowledge("owner", "chat", "event", digest)
            self.assertEqual(box.pending("owner", "chat"), [])
            self.assertIsNone(box.delivery_receipt("owner", "chat", "event"))
            box.close()

if __name__ == "__main__":
    unittest.main()
