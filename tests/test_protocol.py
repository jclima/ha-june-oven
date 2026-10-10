"""Protocol-level tests that do not require Home Assistant."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

PROTOCOL_PATH = (
    Path(__file__).parents[1] / "custom_components" / "june_oven" / "protocol.py"
)
SPEC = importlib.util.spec_from_file_location("june_protocol", PROTOCOL_PATH)
assert SPEC is not None and SPEC.loader is not None
protocol = importlib.util.module_from_spec(SPEC)
# Dataclasses resolve their defining module through sys.modules.
sys.modules[SPEC.name] = protocol
SPEC.loader.exec_module(protocol)

FIXTURES = Path(__file__).parent / "fixtures"


def load_frames(name: str) -> list[dict]:
    """Return the relayed frames in a fixture, each with its capture line."""
    rows = []
    for text in (FIXTURES / name).read_text(encoding="utf-8").splitlines():
        row = json.loads(text)
        rows.append({**row["frame"], "line": row["line"], "dir": row["dir"]})
    return rows


def frame_at(name: str, line: int) -> dict:
    """Return the fixture frame taken from one capture line."""
    return next(frame for frame in load_frames(name) if frame["line"] == line)


def rest_status(case: str) -> dict:
    """Return one recorded REST status response from rest-status.json."""
    return json.loads((FIXTURES / "rest-status.json").read_text(encoding="utf-8"))[case]


def june_local_status(
    connection_state: str, device_state: dict, cook_plan: dict | None
) -> dict:
    """Build a status response exactly as june-local's rest.go does."""
    online = connection_state == "connected"
    return {
        "connection_state": connection_state,
        "online": online,
        "ha_connection_state": "online" if online else "offline",
        "device_state": device_state,
        "device_state_data": {"data": device_state},
        "cook_plan": cook_plan,
        "cook_plan_data": {"data": cook_plan} if cook_plan is not None else None,
        "success": True,
    }


class ProtocolHelpersTest(unittest.TestCase):
    """Verify deterministic protocol helpers."""

    def test_temperature_conversion(self) -> None:
        self.assertEqual(protocol.fahrenheit_to_millic(350), 176667)
        self.assertAlmostEqual(protocol.millic_to_celsius(176667), 176.667)
        self.assertEqual(protocol.celsius_to_fahrenheit(100), 212)

    def test_pairing_code_has_valid_damm_check_digit(self) -> None:
        shown = protocol.build_shown_code("12345", 67)
        self.assertEqual(shown, "12345671")
        self.assertEqual(protocol.damm(shown), 0)

    def test_order_is_strictly_increasing(self) -> None:
        orders = protocol.OrderGenerator()
        self.assertEqual(orders.next(1000), 1000)
        self.assertEqual(orders.next(1000), 1001)
        self.assertEqual(orders.next(999), 1002)

    def test_srp_group_and_deterministic_public_value(self) -> None:
        self.assertEqual(protocol.SRP_N.bit_length(), 8192)
        server = protocol.SrpServer(
            "12345678",
            salt=bytes(range(16)),
            secret_b=123456789,
        )
        self.assertEqual(server.salt_base64, "AAECAwQFBgcICQoLDA0ODw==")
        self.assertEqual(
            hashlib.sha256(server.public_base64.encode()).hexdigest(),
            "5e52eddb66d2e5956848cff9c169f2ad7baf5d18ccf71aa990abef833f568f16",
        )

    def test_signed_frame_wire_shape(self) -> None:
        try:
            from nacl.signing import SigningKey
        except ImportError:
            self.skipTest("PyNaCl is not installed")

        key = SigningKey.generate()
        identity = {
            "oven_id": "oven",
            "device_id": "companion",
            "device_name": "Home Assistant",
            "ed25519_seed_hex": bytes(key).hex(),
        }
        encoded = protocol.build_signed_frame(
            identity,
            protocol.MC_CANCEL,
            {"plan_id": 0},
            order=42,
            now_ms=1000,
        )
        frame = json.loads(encoded)
        signature = base64.b64decode(frame["signature"])
        self.assertEqual(len(signature), 72)
        expected_fingerprint = hashlib.blake2b(
            key.verify_key.encode(), digest_size=8
        ).digest()
        self.assertEqual(signature[:8], expected_fingerprint)

        frame["signature"] = ""
        payload = json.dumps(frame, separators=(",", ":"), ensure_ascii=False).encode()
        key.verify_key.verify(payload, signature[8:])


class EndpointTest(unittest.TestCase):
    """Verify one configured endpoint derives every service URL."""

    def test_normalize_accepts_hosts_addresses_and_ports(self) -> None:
        cases = {
            "": "",
            "   ": "",
            "192.168.1.75": "https://192.168.1.75",
            " 192.168.1.75/ ": "https://192.168.1.75",
            "June-Oven.local": "https://june-oven.local",
            "june-oven.local.": "https://june-oven.local",
            "192.168.1.75:443": "https://192.168.1.75",
            "192.168.1.75:8443": "https://192.168.1.75:8443",
            "https://oven.lan": "https://oven.lan",
            "HTTPS://oven.lan:443/": "https://oven.lan",
            "http://192.168.1.75": "http://192.168.1.75:8080",
            "http://192.168.1.75:80": "http://192.168.1.75:80",
            "fe80::1": "https://[fe80::1]",
            "[fe80::1]:8443": "https://[fe80::1]:8443",
            "http://[FE80::0001]": "http://[fe80::1]:8080",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(protocol.normalize_endpoint(value), expected)
                # Stored values are normalized again on load.
                self.assertEqual(protocol.normalize_endpoint(expected), expected)

    def test_normalize_rejects_invalid_values(self) -> None:
        for value in (
            "ftp://oven.local",
            "wss://oven.local",
            "oven.local/local/status",
            "user:secret@oven.local",
            "oven.local:99999",
            "oven.local:port",
            "-oven.local",
            "oven_local",
            "oven local",
            "https://",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                protocol.normalize_endpoint(value)

    def test_empty_endpoint_uses_public_cloud(self) -> None:
        endpoints = protocol.build_endpoints("")
        self.assertFalse(endpoints.local)
        self.assertEqual(endpoints.api_url, "https://api.junelife.com")
        self.assertEqual(endpoints.messaging_url, "https://messaging.junelife.com")
        self.assertEqual(
            endpoints.ws_url,
            "wss://messaging.junelife.com/1/messaging/websocket/companion",
        )

    def test_local_endpoint_derives_every_url(self) -> None:
        endpoints = protocol.build_endpoints("192.168.1.75")
        self.assertTrue(endpoints.local)
        self.assertEqual(endpoints.api_url, "https://192.168.1.75")
        self.assertEqual(endpoints.messaging_url, "https://192.168.1.75")
        self.assertEqual(
            endpoints.ws_url,
            "wss://192.168.1.75/1/messaging/websocket/companion",
        )
        self.assertEqual(endpoints.status_url, "https://192.168.1.75/local/status")

    def test_plain_http_endpoint_uses_plain_websocket(self) -> None:
        endpoints = protocol.build_endpoints("http://192.168.1.75")
        self.assertEqual(endpoints.api_url, "http://192.168.1.75:8080")
        self.assertEqual(
            endpoints.ws_url,
            "ws://192.168.1.75:8080/1/messaging/websocket/companion",
        )

    def test_local_media_url_is_rehomed_to_endpoint(self) -> None:
        endpoints = protocol.build_endpoints("192.168.1.75")
        self.assertEqual(
            endpoints.local_media_url(
                "https://api.junelife.com/media/prod/images/latest.jpg?ts=12"
            ),
            "https://192.168.1.75/media/prod/images/latest.jpg?ts=12",
        )
        self.assertEqual(
            endpoints.local_media_url(
                "http://10.0.0.9:8080/media/prod/images/latest.jpg"
            ),
            "https://192.168.1.75/media/prod/images/latest.jpg",
        )
        for candidate in (
            None,
            42,
            "https://api.junelife.com/2/devices/register",
            "https://api.junelife.com/media/../2/devices/pairing",
        ):
            with self.subTest(candidate=candidate):
                self.assertIsNone(endpoints.local_media_url(candidate))

    def test_cloud_endpoints_do_not_rehome_media(self) -> None:
        self.assertIsNone(
            protocol.build_endpoints("").local_media_url(
                "https://api.junelife.com/media/prod/images/latest.jpg"
            )
        )


class CookProgressTest(unittest.TestCase):
    """Parse 10013 cook_state_data as relayed from a real oven."""

    def test_preheat_percentage_is_already_zero_to_hundred(self) -> None:
        # The cavity had covered 1% of the 25.2 to 176.7 C gap at 26.7 C.
        frame = frame_at("bake-timer-temperature.jsonl", 284)
        self.assertEqual(frame["data"]["sensor_data"]["cavity"], 26700)
        progress = protocol.parse_cook_progress(frame["data"]["cook_state_data"])
        self.assertEqual(progress.label_type, "temperature")
        self.assertAlmostEqual(progress.percent, 0.99031466)
        self.assertIsNone(progress.elapsed_ms)

    def test_holding_reports_one_hundred_percent(self) -> None:
        frame = frame_at("preheat-complete.jsonl", 281)
        progress = protocol.parse_cook_progress(frame["data"]["cook_state_data"])
        self.assertEqual(progress.label_type, "temperature")
        self.assertEqual(progress.percent, 100.0)

    def test_cooking_reports_time_and_elapsed(self) -> None:
        frame = frame_at("oven-screen-proof.jsonl", 367)
        progress = protocol.parse_cook_progress(frame["data"]["cook_state_data"])
        self.assertEqual(progress.label_type, "time")
        self.assertEqual(progress.percent, 0.0)
        self.assertEqual(progress.elapsed_ms, 8003)

    def test_elapsed_falls_back_to_time_label(self) -> None:
        progress = protocol.parse_cook_progress(
            {"progress": {"label_type": "time", "label_value": 4000}}
        )
        self.assertEqual(progress.elapsed_ms, 4000)
        self.assertIsNone(progress.percent)

    def test_out_of_range_and_invalid_values(self) -> None:
        self.assertEqual(
            protocol.parse_cook_progress({"progress": {"percentage": 104.2}}).percent,
            100.0,
        )
        self.assertIsNone(
            protocol.parse_cook_progress({"progress": {"percentage": True}}).percent
        )
        self.assertIsNone(protocol.parse_cook_progress(None))
        self.assertIsNone(protocol.parse_cook_progress([1]))


class CookPlanTest(unittest.TestCase):
    """Parse cook plans from 10013-10016 frames."""

    def test_companion_bake_plan(self) -> None:
        plan = protocol.parse_cook_plan(
            frame_at("bake-timer-temperature.jsonl", 250)["data"]
        )
        self.assertEqual(plan.plan_id, 0)
        self.assertEqual(plan.name, "bake")
        self.assertEqual(plan.session_id, "b8144d30-3e0c-478e-a731-b2da799a9170")
        self.assertEqual(plan.presentation_type, "preheat")
        self.assertEqual(plan.target_millic, 176667)

    def test_telemetry_carries_the_same_plan(self) -> None:
        started = frame_at("bake-timer-temperature.jsonl", 250)
        telemetry = frame_at("bake-timer-temperature.jsonl", 251)
        self.assertEqual(
            protocol.parse_cook_plan(telemetry["data"]["cook_plan_data"]),
            protocol.parse_cook_plan(started["data"]),
        )

    def test_target_comes_from_current_step(self) -> None:
        # After 11005 the first step still says 350 F; the current one is 325 F.
        data = frame_at("bake-timer-temperature.jsonl", 291)["data"]
        self.assertEqual(data["food"]["plan"]["steps"][0]["temperature_cavity"], 176667)
        plan = protocol.parse_cook_plan(data)
        self.assertEqual(plan.target_millic, 162778)
        self.assertEqual(plan.presentation_type, "preheat")

    def test_oven_screen_program_plan(self) -> None:
        plan = protocol.parse_cook_plan(
            frame_at("oven-screen-proof.jsonl", 344)["data"]
        )
        self.assertEqual(plan.plan_id, 114)
        self.assertEqual(plan.name, "proof")
        self.assertEqual(plan.presentation_type, "cook_unbound")
        self.assertEqual(plan.target_millic, 26667)

    def test_off_step_has_no_target(self) -> None:
        data = frame_at("bake-timer-temperature.jsonl", 281)["data"]
        data = {**data, "step_state": {"step_id": 4, "step_index": 3}}
        plan = protocol.parse_cook_plan(data)
        self.assertEqual(plan.presentation_type, "complete_and_off")
        self.assertIsNone(plan.target_millic)

    def test_invalid_plans(self) -> None:
        for value in (None, [], {}, {"food": "bake"}, {"plan_id": 0}):
            with self.subTest(value=value):
                self.assertIsNone(protocol.parse_cook_plan(value))
        plan = protocol.parse_cook_plan(
            {"food": {"name": "bake"}, "step_state": {"step_index": 5}}
        )
        self.assertEqual(plan.name, "bake")
        self.assertIsNone(plan.plan_id)
        self.assertIsNone(plan.target_millic)


class StatusTest(unittest.TestCase):
    """Parse REST status snapshots."""

    def test_june_local_connected(self) -> None:
        cook_plan = frame_at("oven-screen-proof.jsonl", 344)["data"]
        status = protocol.parse_status(
            june_local_status("connected", {"state": "active"}, cook_plan)
        )
        self.assertTrue(status.online)
        self.assertEqual(status.device_state, "active")
        self.assertEqual(status.cook_plan.plan_id, 114)

    def test_june_local_disconnected(self) -> None:
        status = protocol.parse_status(
            june_local_status("disconnected", {"state": "idle"}, None)
        )
        self.assertFalse(status.online)
        self.assertEqual(status.device_state, "idle")
        self.assertIsNone(status.cook_plan)

    def test_wrapped_aliases_and_cloud_states(self) -> None:
        cook_plan = frame_at("bake-timer-temperature.jsonl", 250)["data"]
        status = protocol.parse_status(
            {
                "connection_state": "online",
                "device_state": {"data": {"state": "active"}},
                "cook_plan": {"data": cook_plan},
            }
        )
        self.assertTrue(status.online)
        self.assertEqual(status.device_state, "active")
        self.assertEqual(status.cook_plan.target_millic, 176667)

        status = protocol.parse_status(
            {
                "ha_connection_state": "offline",
                "device_state_data": {"data": {"state": "idle"}},
                "cook_plan_data": {"data": cook_plan},
            }
        )
        self.assertFalse(status.online)
        self.assertEqual(status.device_state, "idle")
        self.assertEqual(status.cook_plan.name, "bake")

        status = protocol.parse_status({"connection_state": "pairing"})
        self.assertIsNone(status.online)
        self.assertIsNone(status.device_state)

    def test_recorded_june_local_idle(self) -> None:
        status = protocol.parse_status(rest_status("june_local_idle"))
        self.assertTrue(status.online)
        self.assertEqual(status.device_state, "idle")
        self.assertIsNone(status.cook_plan)

    def test_recorded_june_local_active(self) -> None:
        status = protocol.parse_status(rest_status("june_local_active"))
        self.assertTrue(status.online)
        self.assertEqual(status.device_state, "active")
        self.assertEqual(status.cook_plan.plan_id, 114)
        self.assertEqual(status.cook_plan.name, "proof")

    def test_recorded_cloud_active(self) -> None:
        status = protocol.parse_status(rest_status("cloud_active"))
        self.assertTrue(status.online)
        self.assertEqual(status.device_state, "active")
        self.assertEqual(status.cook_plan.plan_id, 114)

        payload = {**rest_status("cloud_active"), "connection_state": "offline"}
        self.assertFalse(protocol.parse_status(payload).online)

    def test_aliases_take_precedence(self) -> None:
        cook_plan = frame_at("bake-timer-temperature.jsonl", 250)["data"]
        status = protocol.parse_status(
            {
                **rest_status("june_local_active"),
                "ha_connection_state": "offline",
                "online": True,
                "device_state_data": {"data": {"state": "idle"}},
                "cook_plan_data": cook_plan,
            }
        )
        self.assertFalse(status.online)
        self.assertEqual(status.device_state, "idle")
        # A bare cook_plan_data is read as-is.
        self.assertEqual(status.cook_plan.name, "bake")

    def test_aliases_fall_back_when_unusable(self) -> None:
        status = protocol.parse_status(
            {
                **rest_status("june_local_active"),
                "ha_connection_state": "unknown",
                "connection_state": "disconnected",
                "device_state_data": {"data": None},
                "cook_plan_data": None,
            }
        )
        self.assertFalse(status.online)
        self.assertEqual(status.device_state, "active")
        self.assertEqual(status.cook_plan.plan_id, 114)

        status = protocol.parse_status({"online": False})
        self.assertFalse(status.online)


class CookPhaseTest(unittest.TestCase):
    """Summarize the cook phase."""

    def test_phases(self) -> None:
        cases = {
            (False, "preheat", "temperature"): "idle",
            (True, "preheat", "temperature"): "preheating",
            (True, "preheat_and_hold", "temperature"): "preheated",
            (True, "cook_unbound", "time"): "cooking",
            (True, "cook_bound", "time"): "cooking",
            (True, None, "temperature"): "preheating",
            (True, None, "time"): "cooking",
            (True, None, None): "cooking",
        }
        for arguments, expected in cases.items():
            with self.subTest(arguments=arguments):
                self.assertEqual(protocol.cook_phase(*arguments), expected)
                self.assertIn(expected, protocol.COOK_PHASES)


class PreheatWatchTest(unittest.TestCase):
    """Detect preheat completion from replayed oven frames."""

    @staticmethod
    def _replay(name: str) -> list[int]:
        watch = protocol.PreheatWatch()
        fired = []
        for frame in load_frames(name):
            code, data = frame["message_code"], frame["data"]
            if frame["dir"] != "oven":
                continue
            if code == protocol.MC_NOTIFICATION:
                if watch.notification(data):
                    fired.append(frame["line"])
                continue
            if code == protocol.MC_TELEMETRY:
                data = data["cook_plan_data"]
            elif code not in (
                protocol.MC_PLAN_STARTED,
                protocol.MC_PLAN,
                protocol.MC_TEMPERATURE,
            ):
                continue
            if watch.plan(protocol.parse_cook_plan(data)):
                fired.append(frame["line"])
        return fired

    def test_fires_once_when_hold_starts(self) -> None:
        # 10016 moves to preheat_and_hold, a 10015 repeats the preheat step,
        # then 10012 and 10013 confirm it: one event.
        self.assertEqual(self._replay("preheat-complete.jsonl"), [278])

    def test_does_not_fire_while_preheating_or_cooking(self) -> None:
        self.assertEqual(self._replay("bake-timer-temperature.jsonl"), [])
        self.assertEqual(self._replay("oven-screen-proof.jsonl"), [])

    def test_notification_fires_once_per_session(self) -> None:
        notification = frame_at("preheat-complete.jsonl", 280)["data"]
        watch = protocol.PreheatWatch()
        self.assertTrue(watch.notification(notification))
        self.assertFalse(watch.notification(notification))
        self.assertFalse(
            watch.notification({"notification_id": "NOTIFICATION_COOK_COMPLETE"})
        )

    def test_plan_first_seen_holding_does_not_fire(self) -> None:
        holding = protocol.parse_cook_plan(
            frame_at("preheat-complete.jsonl", 281)["data"]["cook_plan_data"]
        )
        watch = protocol.PreheatWatch()
        self.assertFalse(watch.plan(holding))
        self.assertFalse(watch.plan(holding))


if __name__ == "__main__":
    unittest.main()
