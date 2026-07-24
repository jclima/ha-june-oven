"""Protocol-level tests that do not require Home Assistant."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

PROTOCOL_PATH = (
    Path(__file__).parents[1] / "custom_components" / "june_oven" / "protocol.py"
)
SPEC = importlib.util.spec_from_file_location("june_protocol", PROTOCOL_PATH)
assert SPEC is not None and SPEC.loader is not None
protocol = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(protocol)


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


if __name__ == "__main__":
    unittest.main()
