"""Server rules for static files. Run from the project root: python -m unittest"""
import unittest

from dupfinder.server import STATIC_RE


class StaticPathTest(unittest.TestCase):
    def test_file_della_build_ammessi(self):
        for p in ("/favicon.svg", "/assets/index-21OXHFiY.js", "/assets/geist-latin-wght-normal-BgDaEnEv.woff2"):
            self.assertTrue(STATIC_RE.match(p), p)

    def test_percorsi_fuori_dalla_build_rifiutati(self):
        for p in ("/../server.py", "/assets/../../config.py", "/assets/x/y.js", "/..", "/a..b",
                  "/assets\\..\\x.js", "/C:/Windows/win.ini", "/api/config", "/noext"):
            self.assertFalse(STATIC_RE.match(p), p)


if __name__ == "__main__":
    unittest.main()
