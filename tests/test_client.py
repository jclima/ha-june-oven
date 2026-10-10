"""Replay relayed oven frames through the client without Home Assistant."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from typing import Any

from test_protocol import frame_at, june_local_status, load_frames, rest_status

INTEGRATION = Path(__file__).parents[1] / "custom_components" / "june_oven"
PACKAGE = "june_oven_under_test"


def _load_api() -> types.ModuleType:
    """Import api.py as part of the integration package, skipping __init__."""
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(INTEGRATION)]
    sys.modules[PACKAGE] = package
    stub = None
    if importlib.util.find_spec("aiohttp") is None:
        # The client only needs these names to import; nothing here uses them.
        stub = types.ModuleType("aiohttp")
        for name in ("ClientResponse", "ClientSession", "ClientWebSocketResponse"):
            setattr(stub, name, type(name, (), {}))
        stub.ClientError = type("ClientError", (Exception,), {})
        stub.ClientSSLError = type("ClientSSLError", (stub.ClientError,), {})
        stub.WSServerHandshakeError = type(
            "WSServerHandshakeError", (stub.ClientError,), {}
        )
        stub.WSMsgType = types.SimpleNamespace(TEXT=1, CLOSE=8, CLOSED=257, ERROR=258)
        sys.modules["aiohttp"] = stub
    try:
        return importlib.import_module(f"{PACKAGE}.api")
    finally:
        if stub is not None:
            del sys.modules["aiohttp"]


api = _load_api()

IDENTITY = api.JuneIdentity(
    oven_id="oven",
    device_id="companion",
    device_name="Home Assistant",
    password="",
    ed25519_seed_hex="00" * 32,
    access_token="",
    refresh_token="",
)


class ClientReplayTest(unittest.IsolatedAsyncioTestCase):
    """Feed oven frames to JuneClient in receive order."""

    async def asyncSetUp(self) -> None:
        self.client = api.JuneClient(None, IDENTITY)
        self.sent: list[tuple[int, dict[str, Any]]] = []
        self.statuses: list[str | None] = []
        self.pulses: list[str] = []
        self.replayed: dict[str, int] = {}
        start_pulse = self.client._start_pulse

        def record_pulse(field: str) -> None:
            self.pulses.append(field)
            start_pulse(field)

        async def send_command(code: int, data: dict[str, Any]) -> str | None:
            self.sent.append((code, dict(data)))
            return self.statuses.pop(0) if self.statuses else "success"

        self.client._start_pulse = record_pulse
        self.client._async_send_command = send_command

    async def asyncTearDown(self) -> None:
        await self.client.async_stop()

    def replay(self, name: str, *, until: int | None = None) -> None:
        """Handle a fixture's next oven frames, through a capture line."""
        for frame in load_frames(name):
            if frame["line"] <= self.replayed.get(name, 0):
                continue
            if until is not None and frame["line"] > until:
                return
            self.replayed[name] = frame["line"]
            if frame["dir"] == "oven" and frame["message_code"] != api.MC_ACK:
                self.client._handle_message(json.dumps(frame))

    async def test_companion_bake_with_timer_and_temperature_change(self) -> None:
        state = self.client.state
        self.replay("bake-timer-temperature.jsonl", until=250)
        self.assertTrue(state.active)
        self.assertEqual(state.connection_state, "online")
        self.assertEqual(state.cook_mode, "bake")
        self.assertEqual(state.plan_id, 0)
        self.assertAlmostEqual(state.target_temp_c, 176.667)
        self.assertEqual(state.cook_phase, "preheating")

        self.replay("bake-timer-temperature.jsonl", until=284)
        self.assertAlmostEqual(state.progress_percent, 0.99031466)
        self.assertAlmostEqual(state.current_temp_c, 26.7)
        self.assertIsNone(state.cook_elapsed_s)
        self.assertFalse(state.ready)

        # The companion lowered the target to 325 F with 11005 at line 289.
        await self.client.async_set_target_f(325, "bake")
        self.assertEqual(
            self.sent,
            [
                (
                    api.MC_SET_TEMPERATURE,
                    frame_at("bake-timer-temperature.jsonl", 289)["data"],
                )
            ],
        )
        self.replay("bake-timer-temperature.jsonl", until=304)
        self.assertAlmostEqual(state.target_temp_c, 162.778)
        self.assertAlmostEqual(state.progress_percent, 0.0)

        self.replay("bake-timer-temperature.jsonl")
        self.assertFalse(state.active)
        self.assertEqual(state.cook_phase, "idle")
        self.assertIsNone(state.progress_percent)
        self.assertFalse(state.done)
        self.assertEqual(self.pulses, [])
        # Companion primitives stay selected for the next start.
        self.assertEqual(state.cook_mode, "bake")

    async def test_preheat_complete_pulses_ready_once(self) -> None:
        state = self.client.state
        self.replay("preheat-complete.jsonl", until=277)
        self.assertEqual(state.cook_phase, "preheating")
        self.replay("preheat-complete.jsonl", until=278)
        self.assertTrue(state.ready)
        self.assertAlmostEqual(state.target_temp_c, 37.778)
        self.replay("preheat-complete.jsonl", until=281)
        self.assertEqual(state.cook_phase, "preheated")
        self.assertEqual(state.progress_percent, 100.0)
        self.assertEqual(self.pulses, ["ready"])

    async def test_oven_screen_proof(self) -> None:
        state = self.client.state
        self.replay("oven-screen-proof.jsonl", until=251)
        # This 10018 is stamped with the oven's 2022 clock; it still applies.
        self.assertEqual(state.connection_state, "online")
        self.assertFalse(state.active)

        self.replay("oven-screen-proof.jsonl", until=345)
        self.assertTrue(state.active)
        self.assertEqual(state.cook_mode, "proof")
        self.assertEqual(state.plan_id, 114)
        self.assertAlmostEqual(state.target_temp_c, 26.667)
        self.assertEqual(state.cook_phase, "cooking")
        self.assertEqual(state.cook_elapsed_s, 1.0)

        # The oven refused 11005 at line 352 (plan_id 0) as not-allowed. The
        # plan id is now echoed; a refusal of a program the integration cannot
        # restart must not cancel it.
        self.statuses = ["not-allowed"]
        with self.assertRaises(api.JuneCommandError):
            await self.client.async_set_target_f(100, "proof")
        self.assertEqual(
            self.sent,
            [
                (
                    api.MC_SET_TEMPERATURE,
                    {
                        **frame_at("oven-screen-proof.jsonl", 352)["data"],
                        "plan_id": 114,
                    },
                )
            ],
        )

        self.replay("oven-screen-proof.jsonl")
        self.assertEqual(state.cook_elapsed_s, 8.003)

        await self.client.async_set_timer(10)
        await self.client.async_cancel()
        self.assertEqual(
            self.sent[1:],
            [
                (api.MC_SET_TIMER, {"plan_id": 114, "duration": 600000}),
                (api.MC_CANCEL, {"plan_id": 114}),
            ],
        )

        self.client._handle_message(
            json.dumps({"message_code": 10018, "data": {"state": "idle"}})
        )
        self.assertFalse(state.done)
        self.assertEqual(state.plan_id, 0)
        # The climate entity falls back to its defaults after a program ends.
        self.assertIsNone(state.cook_mode)
        self.assertIsNone(state.target_temp_c)

    async def test_refused_temperature_change_restarts_a_primitive(self) -> None:
        self.replay("bake-timer-temperature.jsonl", until=250)
        self.statuses = ["not-allowed", "success", "success"]
        await self.client.async_set_target_f(325, "bake")
        self.assertEqual(
            [code for code, _ in self.sent],
            [api.MC_SET_TEMPERATURE, api.MC_CANCEL, api.MC_PREHEAT],
        )
        self.assertEqual(
            self.sent[2][1], {"primitive_type": "bake", "temperature_cavity": 162778}
        )

    async def test_unacknowledged_temperature_change_does_not_restart(self) -> None:
        self.replay("bake-timer-temperature.jsonl", until=250)
        self.statuses = [None]
        with self.assertRaises(api.JuneCommandError):
            await self.client.async_set_target_f(325, "bake")
        self.assertEqual(len(self.sent), 1)

    async def test_rest_status_from_june_local(self) -> None:
        state = self.client.state
        cook_plan = frame_at("oven-screen-proof.jsonl", 344)["data"]
        self.client._apply_status(
            june_local_status("connected", {"state": "active"}, cook_plan)
        )
        self.assertTrue(state.online)
        self.assertTrue(state.active)
        self.assertEqual(state.plan_id, 114)
        self.assertEqual(state.cook_mode, "proof")

        # june-local keeps the last plan after the cook ends.
        self.client._apply_status(
            june_local_status("disconnected", {"state": "idle"}, cook_plan)
        )
        self.assertEqual(state.connection_state, "offline")
        self.assertFalse(state.online)
        self.assertFalse(state.active)
        self.assertEqual(state.plan_id, 0)
        self.assertIsNone(state.cook_mode)

    async def test_recorded_rest_statuses(self) -> None:
        state = self.client.state
        self.client._apply_status(rest_status("june_local_active"))
        self.assertEqual(state.connection_state, "online")
        self.assertTrue(state.active)
        self.assertEqual(state.plan_id, 114)
        self.assertEqual(state.cook_mode, "proof")

        self.client._apply_status(rest_status("june_local_idle"))
        self.assertEqual(state.connection_state, "online")
        self.assertFalse(state.active)
        self.assertIsNone(state.cook_mode)

        self.client._apply_status(rest_status("cloud_active"))
        self.assertEqual(state.connection_state, "online")
        self.assertTrue(state.active)
        self.assertEqual(state.plan_id, 114)

        # Only the canonical value is stored, never "disconnected".
        self.client._apply_status(
            {"connection_state": "disconnected", "device_state": {"state": "idle"}}
        )
        self.assertEqual(state.connection_state, "offline")
        self.assertFalse(state.active)

    async def test_local_camera_frames_are_rehomed(self) -> None:
        self.client.endpoints = api.build_endpoints("192.168.1.75")
        # june-local still names api.junelife.com in every 10011.
        for path in ("/media/prod/images/1.jpg?ts=1", "/media/prod/images/2.jpg"):
            self.client._handle_message(
                json.dumps(
                    {
                        "message_code": api.MC_CAMERA,
                        "data": {"image_url": f"https://api.junelife.com{path}"},
                    }
                )
            )
            self.assertEqual(
                self.client.state.snapshot_url, f"https://192.168.1.75{path}"
            )


if __name__ == "__main__":
    unittest.main()
