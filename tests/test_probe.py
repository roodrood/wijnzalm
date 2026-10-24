import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from probe_forums import SITES, markdown_report, SameHostRedirect
from urllib.error import URLError
from urllib.request import Request

class ProbeTests(unittest.TestCase):
    def test_only_two_expected_sites(self):
        self.assertEqual(set(SITES), {"vinejo", "lapassionduvin"})
    def test_markdown(self):
        data = [{"site":"vinejo", "dns":{"ok":False},
                 "homepage":{"http_status":None},
                 "robots":{"http_status":502},
                 "verdict":"needs_investigation"}]
        self.assertIn("502", markdown_report(data))
    def test_external_redirect_rejected(self):
        handler = SameHostRedirect()
        with self.assertRaises(URLError):
            handler.redirect_request(Request("https://www.lapassionduvin.com/"), None,
                                     302, "Moved", {}, "https://other.example/")

if __name__ == "__main__":
    unittest.main()
