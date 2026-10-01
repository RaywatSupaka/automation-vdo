import sys
import unittest
import uuid

from core.secure_store import WindowsCredentialStore


@unittest.skipUnless(sys.platform == "win32", "Windows Credential Manager only")
class SecureStoreTests(unittest.TestCase):
    def test_save_load_and_delete_temporary_credential(self):
        store = WindowsCredentialStore(f"SmartPostAI/Test-{uuid.uuid4().hex}")
        try:
            store.save("temporary-test-key")
            self.assertEqual(store.load(), "temporary-test-key")
            self.assertTrue(store.delete())
            self.assertEqual(store.load(), "")
        finally:
            store.delete()


if __name__ == "__main__":
    unittest.main()
