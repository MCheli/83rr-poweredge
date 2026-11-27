#!/usr/bin/env python3
"""Unit tests for ha-unifi-bandwidth-guard.py (no network).

    python3 -m unittest scripts/test_ha_unifi_bandwidth_guard.py
"""

import importlib.util
import json
import struct
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("bw_guard", Path(__file__).with_name("ha-unifi-bandwidth-guard.py"))
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)

U = "01JQ5R9H52E3Q3HVR1A69A9TDF"


def ent(eid, uid, disabled_by=None, platform="unifi", entry=U):
    return {"entity_id": eid, "unique_id": uid, "disabled_by": disabled_by, "platform": platform, "config_entry_id": entry}


class ToDisable(unittest.TestCase):
    def ids(self, ents, allow=None):
        return [e["entity_id"] for e in g.to_disable(ents, {U}, allow or set(g.DEFAULT_ALLOW))]

    def test_new_client_sensors_are_disabled(self):
        self.assertEqual(self.ids([ent("sensor.phone_rx", "rx-aa:bb:cc:dd:ee:ff"),
                                   ent("sensor.phone_tx", "tx-aa:bb:cc:dd:ee:ff")]),
                         ["sensor.phone_rx", "sensor.phone_tx"])

    def test_allowlisted_clients_kept(self):
        self.assertEqual(self.ids([ent("sensor.83rr_poweredge_rx", "rx-ec:f4:bb:e6:f7:f4"),
                                   ent("sensor.meta_quest_3_tx", "tx-f2:b1:04:d3:3f:0a")]), [])

    def test_already_disabled_left_alone(self):
        self.assertEqual(self.ids([ent("sensor.x_rx", "rx-aa:bb:cc:dd:ee:ff", disabled_by="integration"),
                                   ent("sensor.y_rx", "rx-aa:bb:cc:dd:ee:01", disabled_by="user")]), [])

    def test_other_unifi_entities_untouched(self):
        self.assertEqual(self.ids([
            ent("sensor.usw_pro_24_port_1_rx", "port_rx-d8:b3:70:45:ca:05_1"),
            ent("sensor.udm_se_port_2_poe_power", "poe_power-f4:e2:c6:d2:2a:4c_2"),
            ent("sensor.phone_uptime", "uptime-aa:bb:cc:dd:ee:ff"),
            ent("sensor.livingroomap_clients", "device_clients-f4:e2:c6:a8:41:70"),
            ent("device_tracker.phone", "default-aa:bb:cc:dd:ee:ff"),
            ent("switch.phone_rx", "rx-aa:bb:cc:dd:ee:ff"),
        ]), [])

    def test_other_integrations_untouched(self):
        self.assertEqual(self.ids([ent("sensor.foo_rx", "rx-aa:bb:cc:dd:ee:ff", platform="mqtt", entry="x"),
                                   ent("sensor.bar_rx", "rx-aa:bb:cc:dd:ee:ff", entry="other-entry")]), [])

    def test_allow_override(self):
        allow = g.parse_allow("AA:BB:CC:DD:EE:FF, ")
        self.assertEqual(allow, {"aa:bb:cc:dd:ee:ff"})
        self.assertEqual(self.ids([ent("sensor.phone_rx", "rx-aa:bb:cc:dd:ee:ff"),
                                   ent("sensor.83rr_poweredge_rx", "rx-ec:f4:bb:e6:f7:f4")], allow),
                         ["sensor.83rr_poweredge_rx"])
        self.assertEqual(g.parse_allow(""), g.DEFAULT_ALLOW)


class Frames(unittest.TestCase):
    def unmask(self, frame, header_len):
        mask = frame[header_len:header_len + 4]
        return bytes(b ^ mask[i % 4] for i, b in enumerate(frame[header_len + 4:]))

    def test_small_frame(self):
        p = json.dumps({"type": "auth"}).encode()
        f = g.encode_frame(p, mask=b"\x01\x02\x03\x04")
        self.assertEqual(f[0], 0x81)
        self.assertEqual(f[1], 0x80 | len(p))
        self.assertEqual(self.unmask(f, 2), p)

    def test_medium_and_large_frames(self):
        p = b"x" * 300
        f = g.encode_frame(p, mask=b"\x00\x00\x00\x00")
        self.assertEqual(f[1], 0x80 | 126)
        self.assertEqual(struct.unpack("!H", f[2:4])[0], 300)
        p = b"y" * 70000
        f = g.encode_frame(p, mask=b"\x09\x08\x07\x06")
        self.assertEqual(f[1], 0x80 | 127)
        self.assertEqual(struct.unpack("!Q", f[2:10])[0], 70000)
        self.assertEqual(self.unmask(f, 10), p)


if __name__ == "__main__":
    unittest.main()
