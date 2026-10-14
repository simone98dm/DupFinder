"""Tests for archive-aware deletion, quarantine, session, hash cache, inventory, similar folders,
catalog, extraction, similar images, watcher and API routing. Run: python -m unittest"""
import builtins
import errno
import os
import subprocess
import time
import unittest
import zipfile
from pathlib import Path

from dupfinder import api, config, extract, images, quarantine
from dupfinder.archives import safe_member_path
from dupfinder.catalog import archive_job, restore_job, verify_job
from dupfinder.jobs import Job
from dupfinder.scanner import Scanner
from dupfinder.utils import SEVENZIP
from dupfinder.watcher import Watcher
from tests.test_scanner import Isolated


def run(fn, *args):
    """Runs a job function synchronously."""
    job = Job("test")
    return fn(job, *args)


class ArchiveKeepTest(Isolated):
    def setUp(self):
        super().setUp()
        self.data = os.urandom(5000)
        self.disk = self.write("foto.jpg", self.data)
        self.zip = self.root / "data" / "backup.zip"
        with zipfile.ZipFile(self.zip, "w") as zf:
            zf.writestr("dentro/foto.jpg", self.data)

    def disk_id(self, s):
        return next(f["id"] for f in s.results()["groups"][0]["files"] if not f.get("chain"))

    def test_disk_copy_needs_archive_keep(self):
        s = self.scan()
        fid = self.disk_id(s)
        self.assertEqual(s.delete([fid], "permanent")["deleted"], [])
        self.assertEqual(s.delete([fid], "permanent", arc_keep=True)["deleted"], [fid])
        self.assertFalse(self.disk.exists())

    def test_changed_archive_is_not_a_keeper(self):
        s = self.scan()
        fid = self.disk_id(s)
        with zipfile.ZipFile(self.zip, "a") as zf:
            zf.writestr("altro.txt", b"x" * 100)
        os.utime(self.zip, (time.time() + 10, time.time() + 10))
        self.assertEqual(s.delete([fid], "permanent", arc_keep=True)["deleted"], [])
        self.assertTrue(self.disk.exists())


class QuarantineTest(Isolated):
    def test_quarantine_restore_and_purge(self):
        data = os.urandom(3000)
        a = self.write("a/x.bin", data)
        self.write("b/x.bin", data)
        s = self.scan()
        fid = next(f["id"] for f in s.results()["groups"][0]["files"] if "a" in Path(f["path"]).parts)
        r = s.delete([fid], "quarantine")
        self.assertEqual(r["deleted"], [fid])
        self.assertFalse(a.exists())
        sess = quarantine.sessions()
        self.assertEqual(len(sess), 1)
        self.assertEqual(sess[0]["files"][0]["original"], str(a))
        # a new file in the original place is never overwritten
        a.write_bytes(b"new")
        self.assertEqual(len(quarantine.restore(sess[0]["id"])["errors"]), 1)
        a.unlink()
        self.assertEqual(quarantine.restore(sess[0]["id"])["restored"], [str(a)])
        self.assertEqual(a.read_bytes(), data)
        self.assertEqual(quarantine.sessions(), [])

    def test_purge(self):
        data = os.urandom(3000)
        self.write("a/x.bin", data)
        self.write("b/x.bin", data)
        s = self.scan()
        s.delete([s.results()["groups"][0]["files"][0]["id"]], "quarantine")
        sid = quarantine.sessions()[0]["id"]
        self.assertEqual(quarantine.purge(sid)["errors"], [])
        self.assertEqual(quarantine.sessions(), [])

    def test_session_id_validated(self):
        for bad in ("0/../x", "9/abc", "x/abc", "0/"):
            with self.assertRaises(ValueError):
                quarantine.restore(bad)


class SessionCacheInventoryTest(Isolated):
    def test_session_survives_restart_with_selection(self):
        data = os.urandom(3000)
        self.write("a.bin", data)
        self.write("b.bin", data)
        s = self.scan()
        ids = [f["id"] for f in s.results()["groups"][0]["files"]]
        s.set_selection(s.started, ids[:1])
        s2 = Scanner(self.catalog)
        self.assertTrue(s2.load_session())
        self.assertEqual(s2.results()["groups"], s.results()["groups"])
        self.assertEqual(s2.results()["selection"], ids[:1])
        self.assertEqual(s2.delete(ids[:1], "permanent")["deleted"], ids[:1])

    def test_second_scan_uses_hash_cache(self):
        big = os.urandom(300 * 1024)
        self.write("a.bin", big)
        self.write("b.bin", big)
        self.assertEqual(self.scan().cache_hits, 0)
        s = self.scan()
        self.assertEqual(s.cache_hits, 2)
        self.assertEqual(len(s.results()["groups"]), 1)

    def test_changed_file_is_rehashed(self):
        big = os.urandom(300 * 1024)
        self.write("a.bin", big)
        b = self.write("b.bin", big)
        self.scan()
        b.write_bytes(big[:-1] + bytes([big[-1] ^ 1]))       # same size, new content
        os.utime(b, (time.time() + 5, time.time() + 5))
        self.assertEqual(self.scan().results()["groups"], [])

    def test_inventory_and_similar_folders(self):
        files = [os.urandom(2000 + i) for i in range(4)]
        for i, d in enumerate(files):
            self.write(f"Foto/{i}.jpg", d)
        for i, d in enumerate(files[:3]):
            self.write(f"Backup/IMG_{i}.jpg", d)          # Backup is fully contained in Foto
        self.write("Docs/nota.txt", b"hello")
        r = self.scan().results()
        inv = r["inventory"]
        self.assertEqual(inv["files"], 8)
        self.assertEqual(dict((e[0], e[1]) for e in inv["ext"])[".jpg"], 7)
        self.assertEqual(len(inv["largest"]), 8)
        top = r["folders"][0]
        self.assertTrue(top["dir"].endswith("Backup") and top["other"].endswith("Foto"))
        self.assertEqual((top["shared"], top["total"]), (3, 3))
        foto = next(f for f in r["folders"] if f["dir"].endswith("Foto"))
        self.assertEqual((foto["shared"], foto["total"]), (3, 4))


class CatalogTest(Isolated):
    def test_archive_incremental_search_verify_restore(self):
        a = self.write("src/a.txt", b"alpha" * 1000)
        self.write("src/sub/b.jpg", os.urandom(4000))
        self.write("src/dup_of_a.txt", b"alpha" * 1000)
        dest = self.root / "archives"
        r = run(archive_job, self.catalog, [str(self.root / "data" / "src")], str(dest))
        self.assertEqual((r["files"], r["already"]), (2, 1))       # the duplicate is stored once
        self.assertTrue(os.path.isfile(r["archive"]))
        self.assertFalse(list(dest.glob("*.part")))
        # second run: nothing new
        r2 = run(archive_job, self.catalog, [str(self.root / "data" / "src")], str(dest))
        self.assertEqual((r2["files"], r2["archive"]), (0, ""))
        hits = self.catalog.search("a.txt")
        self.assertEqual(len(hits), 1)
        self.assertEqual(run(verify_job, self.catalog, None)[0]["status"], "ok")
        # restore: never over an existing file, fine elsewhere
        rr = run(restore_job, self.catalog, [hits[0]["id"]], None)
        self.assertEqual(len(rr["errors"]), 1)
        a.unlink()
        rr = run(restore_job, self.catalog, [hits[0]["id"]], None)
        self.assertEqual(rr["restored"], [str(a)])
        self.assertEqual(a.read_bytes(), b"alpha" * 1000)

    def test_verify_detects_damage(self):
        self.write("src/a.bin", os.urandom(50000))
        r = run(archive_job, self.catalog, [str(self.root / "data" / "src")], str(self.root / "arc"))
        z = Path(r["archive"])
        z.write_bytes(z.read_bytes()[:2000])
        self.assertEqual(run(verify_job, self.catalog, None)[0]["status"], "damaged")

    def test_not_enough_space(self):
        self.write("src/a.bin", os.urandom(5000))
        old = config.SPACE_MARGIN
        config.SPACE_MARGIN = 1 << 62
        try:
            with self.assertRaisesRegex(ValueError, "Not enough space"):
                run(archive_job, self.catalog, [str(self.root / "data" / "src")], str(self.root / "arc"))
        finally:
            config.SPACE_MARGIN = old


class ExtractTest(Isolated):
    def setUp(self):
        super().setUp()
        self.dup = os.urandom(4000)
        self.uniq = os.urandom(3000)
        self.write("Foto/a.jpg", self.dup)
        self.zip = self.root / "data" / "old.zip"
        with zipfile.ZipFile(self.zip, "w") as zf:
            zf.writestr("Foto/a.jpg", self.dup)
            zf.writestr("Foto/only_here.jpg", self.uniq)

    def test_plan_and_extract_skipping_duplicates(self):
        s = self.scan()
        p = extract.plan(s, str(self.zip))
        self.assertEqual((p["files"], p["duplicates"], p["need"]), (2, 1, 3000))
        r = run(extract.extract_job, s, str(self.zip), "", True, "quarantine")
        out = Path(extract.default_dest(str(self.zip)))
        self.assertEqual((r["extracted"], r["skipped"], r["complete"]), (1, 1, True))
        self.assertEqual((out / "Foto" / "only_here.jpg").read_bytes(), self.uniq)
        self.assertFalse((out / "Foto" / "a.jpg").exists())
        self.assertFalse(self.zip.exists())                       # moved to quarantine
        self.assertEqual(r["archive_action"], "quarantine")
        self.assertEqual(quarantine.sessions()[0]["files"][0]["original"], str(self.zip))

    def test_name_taken_is_renamed(self):
        s = self.scan()
        out = Path(extract.default_dest(str(self.zip)))
        (out / "Foto").mkdir(parents=True)
        (out / "Foto" / "only_here.jpg").write_bytes(b"something else")
        r = run(extract.extract_job, s, str(self.zip), "", True, "keep")
        self.assertEqual(r["renamed"], 1)
        self.assertEqual((out / "Foto" / "only_here (1).jpg").read_bytes(), self.uniq)
        self.assertTrue(self.zip.exists())

    def test_zip_slip_member_not_extracted_and_archive_kept(self):
        with zipfile.ZipFile(self.zip, "a") as zf:
            zf.writestr("../../evil.txt", b"evil" * 100)
        s = self.scan()
        r = run(extract.extract_job, s, str(self.zip), "", True, "quarantine")
        self.assertFalse(r["complete"])
        self.assertTrue(self.zip.exists())
        self.assertFalse((self.root / "evil.txt").exists())
        self.assertFalse((self.root / "data" / "evil.txt").exists())

    def test_disk_full_cleans_up_and_keeps_archive(self):
        s = self.scan()
        real_open = builtins.open

        class Full:
            def __init__(self, f): self.f = f
            def write(self, b): raise OSError(errno.ENOSPC, "No space left on device")
            def __enter__(self): return self
            def __exit__(self, *a): self.f.close()

        def fake_open(path, mode="r", *a, **k):
            f = real_open(path, mode, *a, **k)
            return Full(f) if str(path).endswith(".dupfinder-part") else f

        builtins.open = fake_open
        try:
            r = run(extract.extract_job, s, str(self.zip), "", True, "quarantine")
        finally:
            builtins.open = real_open
        self.assertIn("Disk full", r["stopped"])
        self.assertTrue(self.zip.exists())
        out = Path(extract.default_dest(str(self.zip)))
        self.assertEqual(list(out.rglob("*.dupfinder-part")), [])

    def test_not_enough_space_before_starting(self):
        s = self.scan()
        old = config.SPACE_MARGIN
        config.SPACE_MARGIN = 1 << 62
        try:
            with self.assertRaisesRegex(ValueError, "Not enough space"):
                run(extract.extract_job, s, str(self.zip), "", True, "keep")
        finally:
            config.SPACE_MARGIN = old

    def test_changed_archive_refused(self):
        s = self.scan()
        os.utime(self.zip, (time.time() + 10, time.time() + 10))
        with self.assertRaisesRegex(ValueError, "changed after the scan"):
            extract.plan(s, str(self.zip))

    @unittest.skipUnless(SEVENZIP, "7-Zip not installed")
    def test_extract_7z(self):
        src = self.root / "src7"
        (src / "Foto").mkdir(parents=True)
        (src / "Foto" / "a.jpg").write_bytes(self.dup)
        (src / "Foto" / "b.bin").write_bytes(self.uniq)
        (src / "c.bin").write_bytes(os.urandom(70000))
        arc = self.root / "data" / "old.7z"
        subprocess.run([SEVENZIP, "a", "-ms=on", str(arc), "Foto", "c.bin"], cwd=src,
                       capture_output=True, check=True)
        s = self.scan()
        r = run(extract.extract_job, s, str(arc), "", True, "keep")
        out = Path(extract.default_dest(str(arc)))
        self.assertEqual((r["extracted"], r["skipped"], r["complete"]), (2, 1, True))
        self.assertEqual((out / "Foto" / "b.bin").read_bytes(), self.uniq)
        self.assertEqual((out / "c.bin").read_bytes(), (src / "c.bin").read_bytes())

    def test_safe_member_path(self):
        d = str(self.root / "out")
        self.assertIsNone(safe_member_path(d, "../x"))
        self.assertIsNone(safe_member_path(d, "a/../../x"))
        self.assertIsNone(safe_member_path(d, "C:/Windows/x"))
        self.assertEqual(safe_member_path(d, "/abs/x.txt"), os.path.join(os.path.abspath(d), "abs", "x.txt"))
        self.assertEqual(safe_member_path(d, "a\\b.txt"), os.path.join(os.path.abspath(d), "a", "b.txt"))


@unittest.skipUnless(images.available(), "Pillow not installed")
class SimilarImagesTest(Isolated):
    def test_resized_copy_is_similar(self):
        from PIL import Image
        im = Image.new("RGB", (400, 300))
        for x in range(400):
            for y in range(0, 300, 3):
                im.putpixel((x, y), ((x * 7) % 256, (y * 3) % 256, (x * y) % 256))
        a = self.root / "data" / "big.png"
        a.parent.mkdir(parents=True)
        im.save(a)
        im.resize((200, 150)).save(self.root / "data" / "small.jpg", quality=85)
        Image.new("RGB", (300, 300), (250, 250, 250)).save(self.root / "data" / "other.png")
        s = self.scan()
        r = run(images.similar_job, s, self.catalog)
        self.assertEqual(r["groups"], 1)
        g = images.results(s)[0]
        self.assertEqual(os.path.basename(g["files"][0]["path"]), "big.png")      # best first
        self.assertEqual(s.delete([g["files"][1]["id"]], "permanent", similar=True)["deleted"], [g["files"][1]["id"]])


class WatcherApiTest(Isolated):
    def test_watcher_classifies(self):
        w = Watcher(self.catalog)
        f = self.write("inbox/a.txt", b"hello" * 100)
        w._check(str(f), f.stat().st_size, f.stat().st_mtime)
        self.assertEqual(w.status()["events"][-1]["kind"], "new")
        g = self.write("elsewhere/b.txt", b"hello" * 100)
        w._check(str(g), g.stat().st_size, g.stat().st_mtime)
        self.assertEqual(w.status()["events"][-1]["kind"], "copy")
        run(archive_job, self.catalog, [str(self.root / "data" / "elsewhere")], str(self.root / "arc"))
        w._check(str(f), f.stat().st_size, f.stat().st_mtime)
        self.assertEqual(w.status()["events"][-1]["kind"], "archived")

    def test_routes(self):
        code, body, _ = api.route("GET", "/api/config")
        self.assertEqual(code, 200)
        self.assertIn("admin", body)
        self.assertEqual(api.route("GET", "/api/nothing")[0], 404)
        self.assertEqual(api.route("POST", "/api/job/start", {"kind": "nope"})[0], 400)
        self.assertEqual(api.route("POST", "/api/quarantine/purge", {"id": "0/../../x"})[0], 400)


if __name__ == "__main__":
    unittest.main()
