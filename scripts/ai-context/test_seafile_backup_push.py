"""Tests for the divergence guard of seafile-backup-push.py (no network).

Run: python3 -m unittest scripts/ai-context/test_seafile_backup_push.py
"""

import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "seafile_backup_push", Path(__file__).with_name("seafile-backup-push.py"))
push = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(push)


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


class FindDivergedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name)
        (self.src / "03-diary").mkdir()
        self.now = 1_800_000_000.0
        for name in ("kept.md", "foreign-newer.md", "older.md"):
            p = self.src / "03-diary" / name
            p.write_text("x")
            os.utime(p, (self.now, self.now))

    def tearDown(self):
        self.tmp.cleanup()

    def run_guard(self, remote, state):
        return push.find_diverged(remote, "/", self.src, state, ["/03-diary"])

    def test_classification(self):
        old, new = iso(self.now - 3600), iso(self.now + 3600)
        remote = {
            # renamed/deleted here, Seafile still holds our upload -> stale
            "/03-diary/_month-summary.md": dict(id="our1", mtime=old, size=1),
            # missing here and Seafile's id is not ours -> DIVERGED
            "/03-diary/foreign-new.md": dict(id="theirs", mtime=old, size=1),
            # missing here, no remote_id recorded -> DIVERGED (can't prove it's ours)
            "/03-diary/unknown.md": dict(id="x", mtime=old, size=1),
            # present on both, our version -> fine
            "/03-diary/kept.md": dict(id="our2", mtime=new, size=1),
            # present on both, changed in Seafile by someone else -> DIVERGED
            "/03-diary/foreign-newer.md": dict(id="other", mtime=new, size=2),
            # present on both, Seafile older -> fine
            "/03-diary/older.md": dict(id="other2", mtime=old, size=1),
            # outside the guarded prefix -> ignored
            "/02-systems/gone.md": dict(id="z", mtime=old, size=1),
        }
        state = {
            "03-diary/_month-summary.md": dict(remote_id="our1"),
            "03-diary/foreign-new.md": dict(remote_id="our-old"),
            "03-diary/unknown.md": dict(size=1),
            "03-diary/kept.md": dict(remote_id="our2"),
            "03-diary/foreign-newer.md": dict(remote_id="our3"),
        }
        diverged, stale = self.run_guard(remote, state)
        self.assertEqual(stale, {"03-diary/_month-summary.md"})
        self.assertEqual(diverged, {
            "03-diary/foreign-new.md": "missing on this server",
            "03-diary/unknown.md": "missing on this server",
            "03-diary/foreign-newer.md": "Seafile copy is newer and not ours",
        })


if __name__ == "__main__":
    unittest.main()
