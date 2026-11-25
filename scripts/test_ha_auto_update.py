#!/usr/bin/env python3
"""Unit tests for the planning logic of ha-auto-update.py (no network).

    python3 -m unittest scripts/test_ha_auto_update.py
"""

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location("ha_auto_update", Path(__file__).with_name("ha-auto-update.py"))
hau = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hau)

NOW = datetime(2026, 11, 25, 9, 15, tzinfo=timezone.utc)


def ent(eid, installed, latest, title=None, state=None, skipped=None, features=29, in_progress=False):
    return {"entity_id": eid, "state": state or ("on" if installed != latest else "off"),
            "last_updated": "2026-11-24T19:13:40+00:00",
            "attributes": {"installed_version": installed, "latest_version": latest, "title": title,
                           "skipped_version": skipped, "supported_features": features, "in_progress": in_progress}}


STATES = [
    ent("update.home_assistant_core_update", "2026.11.2", "2026.11.3", "Home Assistant Core", features=15),
    ent("update.home_assistant_operating_system_update", "18.5", "18.6", "Home Assistant Operating System", features=27),
    ent("update.home_assistant_supervisor_update", "2026.11.0", "2026.11.1", "Home Assistant Supervisor", features=5),
    ent("update.terminal_ssh_update", "10.6.0", "10.7.0", "Terminal & SSH"),
    ent("update.hacs_card", "1.0", "1.1", "Some card"),
    ent("update.udm_se", "6.0.17", "6.0.18", None, features=5),           # UniFi: out of scope
    ent("update.marksnas_dsm_update", "DSM 7.4.1", "DSM 7.4.2", "Synology DSM", features=0),
    ent("sensor.not_an_update", "1", "2"),
]
PLATFORMS = {
    "hassio": {"update.home_assistant_core_update", "update.home_assistant_operating_system_update",
               "update.home_assistant_supervisor_update", "update.terminal_ssh_update"},
    "hacs": {"update.hacs_card"},
}


class CandidatesTest(unittest.TestCase):
    def test_scope_and_order(self):
        c = hau.candidates(STATES, PLATFORMS)
        self.assertEqual([x["kind"] for x in c], ["supervisor", "addon", "hacs", "core", "os"])
        ids = {x["entity_id"] for x in c}
        self.assertNotIn("update.udm_se", ids)
        self.assertNotIn("update.marksnas_dsm_update", ids)

    def test_classify_by_title_when_entity_renamed(self):
        self.assertEqual(hau.classify("update.renamed", "Home Assistant Core", "hassio"), "core")
        self.assertEqual(hau.classify("update.whatever", "Matter Server", "hassio"), "addon")
        self.assertEqual(hau.classify("update.home_assistant_core_update", "x", "hacs"), "hacs")


class DecideTest(unittest.TestCase):
    def cand(self, eid, **kw):
        s = next(x for x in STATES if x["entity_id"] == eid)
        c = hau.candidates([s], PLATFORMS)[0]
        c.update(kw)
        return c

    def test_soak(self):
        c = self.cand("update.terminal_ssh_update")
        self.assertEqual(hau.decide(c, hau.iso(NOW - timedelta(days=2, hours=23)), NOW, 3)[0], "wait")
        self.assertEqual(hau.decide(c, hau.iso(NOW - timedelta(days=3)), NOW, 3)[0], "install")
        self.assertEqual(hau.decide(c, None, NOW, 3)[0], "wait")  # first seen now

    def test_core_x0_held(self):
        c = self.cand("update.home_assistant_core_update", latest="2026.12.0")
        action, reason = hau.decide(c, hau.iso(NOW - timedelta(days=30)), NOW, 3)
        self.assertEqual(action, "hold")
        self.assertIn("X.Y.0", reason)
        c = self.cand("update.home_assistant_core_update", latest="2026.12.1")
        self.assertEqual(hau.decide(c, hau.iso(NOW - timedelta(days=4)), NOW, 3)[0], "install")

    def test_x0_only_held_for_core(self):
        c = self.cand("update.terminal_ssh_update", latest="11.0.0")
        self.assertEqual(hau.decide(c, hau.iso(NOW - timedelta(days=4)), NOW, 3)[0], "install")

    def test_skipped_version(self):
        c = self.cand("update.terminal_ssh_update", skipped="10.7.0", state="off")
        self.assertEqual(hau.decide(c, hau.iso(NOW - timedelta(days=9)), NOW, 3)[0], "hold")

    def test_up_to_date_and_unavailable(self):
        c = self.cand("update.terminal_ssh_update", latest="10.6.0", state="off")
        self.assertEqual(hau.decide(c, None, NOW, 3)[0], "none")
        c = self.cand("update.terminal_ssh_update", state="unavailable", latest=None)
        self.assertEqual(hau.decide(c, None, NOW, 3)[0], "none")


class HistoryTest(unittest.TestCase):
    def rows(self, *versions):
        return [{"last_updated": f"2026-11-{20 + i}T00:00:00+00:00", "attributes": {"latest_version": v}}
                for i, v in enumerate(versions)]

    def test_latest_unbroken_run(self):
        self.assertEqual(hau.first_seen_from_history(self.rows("1", "2", "2", "2"), "2"), "2026-11-21T00:00:00+00:00")
        self.assertEqual(hau.first_seen_from_history(self.rows("2", "1", "2"), "2"), "2026-11-22T00:00:00+00:00")
        self.assertIsNone(hau.first_seen_from_history(self.rows("1", "1"), "2"))
        self.assertIsNone(hau.first_seen_from_history([], "2"))


class MiscTest(unittest.TestCase):
    def test_unavail_limit(self):
        self.assertEqual(hau.unavail_limit(382), 25)
        self.assertEqual(hau.unavail_limit(100), 10)

    def test_is_core_x0(self):
        self.assertTrue(hau.is_core_x0("2026.12.0"))
        self.assertFalse(hau.is_core_x0("2026.12.1"))
        self.assertFalse(hau.is_core_x0("2026.12.0b1"))

    def test_load_env(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("# c\nA=1\nB=\"x=y\"\nC='q'\n\nbad line\n")
        env = hau.load_env(Path(f.name))
        Path(f.name).unlink()
        self.assertEqual(env, {"A": "1", "B": "x=y", "C": "q"})


if __name__ == "__main__":
    unittest.main()
