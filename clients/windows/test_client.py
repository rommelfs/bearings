# SPDX-License-Identifier: AGPL-3.0-or-later
"""Native Windows acceptance checks; no network, enrollment or service changes."""

from pathlib import Path
import sys
import tempfile
import unittest

import bearings_windows as client


@unittest.skipUnless(sys.platform == "win32", "Requires real Windows DPAPI, registry and locking")
class NativeWindowsTests(unittest.TestCase):
    def test_dpapi_roundtrip_tamper_and_no_plaintext(self):
        raw = b"synthetic private device key and inventory"
        encrypted = client.protect(raw)
        self.assertNotIn(raw, encrypted)
        self.assertEqual(client.protect(encrypted, decrypt=True), raw)
        changed = bytearray(encrypted)
        changed[-1] ^= 1
        with self.assertRaises(ValueError):
            client.protect(bytes(changed), decrypt=True)

    def test_state_identity_lock_and_atomic_outbox_survive_reopen(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "private"
            with client.Store(path, initialize=True) as store:
                public = client.public(store.data)
                store.data["counter"] = 42
                store.data["queue"] = ['{"synthetic":"pending"}']
                store.save()
                with self.assertRaises(OSError):
                    with client.Store(path):
                        self.fail("Concurrent state lock acquired")
            with client.Store(path, initialize=True) as store:
                self.assertEqual(client.public(store.data), public)
                self.assertEqual(store.data["counter"], 42)
                self.assertEqual(store.data["queue"], ['{"synthetic":"pending"}'])
            self.assertNotIn(public.encode(), (path / "state.dpapi").read_bytes())

    def test_corruption_does_not_replace_identity(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "private"
            with client.Store(path, initialize=True):
                pass
            encrypted = (path / "state.dpapi").read_bytes()
            (path / "state.dpapi").write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                with client.Store(path, initialize=True):
                    pass
            self.assertEqual((path / "state.dpapi").read_bytes(), b"corrupt")
            self.assertTrue(encrypted)

    def test_real_registry_collection_has_one_os_and_bounded_serialization(self):
        report = client.collect()
        self.assertEqual(report["os"]["id"], "windows")
        self.assertEqual(sum(c["windows"]["kind"] == "os" for c in report["components"]), 1)
        self.assertLessEqual(len(client.packed(report)), client.MAX_BODY)
        self.assertEqual(len({c["key"] for c in report["components"]}), len(report["components"]))
        # Deliberately do not print or upload the runner's software inventory.


if __name__ == "__main__":
    unittest.main()
