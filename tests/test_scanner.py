"""Basic Scanner tests. Run from the project root: python -m unittest"""
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from dupfinder import config
from dupfinder import scanner as scanner_mod
from dupfinder.catalog import Catalog
from dupfinder.scanner import Scanner


class Isolated(unittest.TestCase):
    """Redirects every file DupFinder writes (caches, catalog, session, quarantine) to a temporary folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._saved = (scanner_mod.CACHE_FILE, config.DATA_DIR, config.QUARANTINE_ROOT, config.LEGACY_QUARANTINE)
        scanner_mod.CACHE_FILE = self.root / "cache" / "archive_cache.json"
        config.DATA_DIR = self.root / "appdata"
        config.QUARANTINE_ROOT = self.root / "quarantine"
        config.LEGACY_QUARANTINE = self.root / "legacy_quarantine"
        self.catalog = Catalog()
        self.hdd = False                           # all disks treated as SSD or as HDD
        self._is_hdd = Scanner._is_hdd
        Scanner._is_hdd = lambda s, dev, path: self.hdd   # avoids the PowerShell query (~3 s)

    def tearDown(self):
        self.catalog.close()
        scanner_mod.CACHE_FILE, config.DATA_DIR, config.QUARANTINE_ROOT, config.LEGACY_QUARANTINE = self._saved
        Scanner._is_hdd = self._is_hdd
        self.tmp.cleanup()

    def write(self, rel, data: bytes) -> Path:
        p = self.root / "data" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def scan(self, *roots):
        s = Scanner(self.catalog)
        s.start([str(r) for r in roots] or [str(self.root / "data")])
        s.thread.join(30)
        self.assertEqual(s.state, "done", s.message)
        return s


class ScannerTest(Isolated):
    def names(self, s):
        return [sorted(os.path.basename(f["path"].split(" › ")[-1]) for f in g["files"])
                for g in s.results()["groups"]]

    def test_copie_con_nomi_diversi(self):
        big = os.urandom(300 * 1024)               # over 2*PARTIAL: goes through the full hash
        self.write("a/foto.jpg", big)
        self.write("b/copia di foto.jpg", big)
        self.write("c/quasi.jpg", big[:-1] + bytes([big[-1] ^ 1]))   # differs by one byte
        self.assertEqual(self.names(self.scan()), [["copia di foto.jpg", "foto.jpg"]])

    def test_file_dentro_zip(self):
        data = os.urandom(5000)
        self.write("foto.jpg", data)
        with zipfile.ZipFile(self.root / "data" / "backup.zip", "w") as zf:
            zf.writestr("dentro/foto.jpg", data)
        s = self.scan()
        self.assertEqual(self.names(s), [["foto.jpg", "foto.jpg"]])
        self.assertTrue(any(f.get("chain") for f in s.results()["groups"][0]["files"]))

    def test_hdd_e_ssd_stesso_risultato(self):
        for i in range(20):                        # more files than threads, small and large
            data = os.urandom(1000 + i * 20000)
            self.write(f"a/{i}.bin", data)
            self.write(f"b/{i}.bin", data)
            self.write(f"c/{i}.bin", data[:-1] + b"x")
        with zipfile.ZipFile(self.root / "data" / "z.zip", "w") as zf:
            zf.writestr("0.bin", (self.root / "data/a/0.bin").read_bytes())
        ssd = self.names(self.scan())
        self.hdd = True
        self.assertEqual(ssd, self.names(self.scan()))
        self.assertEqual(len(ssd), 20)

    def test_zip_troncato_segnalato(self):
        data = os.urandom(5000)
        self.write("x.bin", data)
        self.write("y.bin", data)
        z = self.write("rotto.zip", b"")
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("f.bin", os.urandom(100000))
        z.write_bytes(z.read_bytes()[:50000])
        s = self.scan()
        self.assertEqual(len(s.results()["groups"]), 1)
        self.assertTrue(any("rotto.zip" in e["path"] for e in s.errors))

    def test_eliminazione_lascia_una_copia_su_disco(self):
        data = os.urandom(5000)
        self.write("x.bin", data)
        self.write("y.bin", data)
        s = self.scan()
        ids = [f["id"] for f in s.results()["groups"][0]["files"]]
        r = s.delete(ids, "permanent")             # asks to delete all of them: refused
        self.assertEqual((r["deleted"], len(r["errors"])), ([], 2))
        self.assertEqual(s.delete(ids[:1], "permanent")["deleted"], ids[:1])


if __name__ == "__main__":
    unittest.main()
