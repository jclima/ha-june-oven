"""June cloud wire-protocol helpers.

Ported from the MIT-licensed homebridge-june-oven project. These helpers have
no Home Assistant dependency so their serialization and math can be tested in
isolation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
from collections.abc import Mapping
from typing import Any, Final

JUNE_API_URL: Final = "https://api.junelife.com"
JUNE_MESSAGING_URL: Final = "https://messaging.junelife.com"
JUNE_WS_URL: Final = "wss://messaging.junelife.com/1/messaging/websocket/companion"
JUNE_USER_AGENT: Final = "okhttp/4.8.1"
JUNE_APP_VERSION: Final = "1.24.1.11"
JUNE_PLATFORM_VERSION: Final = "34"

# Constants embedded in the official June Android application. They identify
# the application, not a user's June account or oven.
JUNE_CLIENT_ID: Final = "dcxqbcv2dY-G12elqDoAhCP8E12V0zC8XWThT-4U"
JUNE_CLIENT_SECRET: Final = "tmoSUwt3OOZCcfMaIadAGD7-x-qPht85HkCgdvuhTKk1yFtfMcfJEyd"

MC_PREHEAT: Final = 11002
MC_CANCEL: Final = 11004
MC_SET_TIMER: Final = 11006
MC_KEEPALIVE: Final = 11011

MC_CAMERA: Final = 10011
MC_TELEMETRY: Final = 10013
MC_PLAN: Final = 10015
MC_TEMPERATURE: Final = 10016
MC_CANCELLED: Final = 10017
MC_DEVICE_STATE: Final = 10018
MC_ACK: Final = 10020
MC_PAIRING_INFO: Final = 10026
MC_PAIRING_INVALIDATED: Final = 10027

# RFC 5054 8192-bit group used by the June app, with generator 19.
SRP_N_HEX: Final = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74"
    "020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F1437"
    "4FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF05"
    "98DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB"
    "9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF695581718"
    "3995497CEA956AE515D2261898FA051015728E5A8AAAC42DAD33170D04507A33"
    "A85521ABDF1CBA64ECFB850458DBEF0A8AEA71575D060C7DB3970F85A6E1E4C7"
    "ABF5AE8CDB0933D71E8C94E04A25619DCEE3D2261AD2EE6BF12FFA06D98A0864"
    "D87602733EC86A64521F2B18177B200CBBE117577A615D6C770988C0BAD946E2"
    "08E24FA074E5AB3143DB5BFCE0FD108E4B82D120A92108011A723C12A787E6D7"
    "88719A10BDBA5B2699C327186AF4E23C1A946834B6150BDA2583E9CA2AD44CE8"
    "DBBBC2DB04DE8EF92E8EFC141FBECAA6287C59474E6BC05D99B2964FA090C3A2"
    "233BA186515BE7ED1F612970CEE2D7AFB81BDD762170481CD0069127D5B05AA9"
    "93B4EA988D8FDDC186FFB7DC90A6C08F4DF435C93402849236C3FAB4D27C7026"
    "C1D4DCB2602646DEC9751E763DBA37BDF8FF9406AD9E530EE5DB382F413001AE"
    "B06A53ED9027D831179727B0865A8918DA3EDBEBCF9B14ED44CE6CBACED4BB1B"
    "DB7F1447E6CC254B332051512BD7AF426FB8F401378CD2BF5983CA01C64B92EC"
    "F032EA15D1721D03F482D7CE6E74FEF6D55E702F46980C82B5A84031900B1C9E"
    "59E7C97FBEC7E8F323A97A7E36CC88BE0F1D45B7FF585AC54BD407B22B4154AA"
    "CC8F6D7EBF48E1D814CC5ED20F8037E0A79715EEF29BE32806A1D58BB7C5DA76"
    "F550AA3D8A1FBFF0EB19CCB1A313D55CDA56C9EC2EF29632387FE8D76E3C0468"
    "043E8F663F4860EE12BF2D5B0B7474D6E694F91E6DBE115974A3926F12FEE5E4"
    "38777CB6A932DF8CD8BEC4D073B931BA3BC832B68D9DD300741FA7BF8AFC47ED"
    "2576F6936BA424663AAB639C5AE4F5683423B4742BF1C978238F16CBE39D652D"
    "E3FDB8BEFC848AD922222E04A4037C0713EB57A81A23F0C73473FC646CEA306B"
    "4BCBC8862F8385DDFA9D4B7FA2C087E879683303ED5BDD3A062B3CF5B3A278A6"
    "6D2A13F83F44F82DDF310EE074AB6A364597E899A0255DC164F31CC50846851D"
    "F9AB48195DED7EA1B1D510BD7EE74D73FAF36BC31ECFA268359046F4EB879F92"
    "4009438B481C6CD7889A002ED5EE382BC9190DA6FC026E479558E4475677E9AA"
    "9E3050E2765694DFC81F56E880B96E7160C980DD98EDD3DFFFFFFFFFFFFFFFFF"
)
SRP_N: Final = int(SRP_N_HEX, 16)
SRP_G: Final = 19
SRP_PAD_LEN: Final = (SRP_N.bit_length() + 7) // 8

DAMM: Final = (
    (0, 3, 1, 7, 5, 9, 8, 6, 4, 2),
    (7, 0, 9, 2, 1, 5, 4, 8, 6, 3),
    (4, 2, 0, 6, 8, 7, 1, 3, 5, 9),
    (1, 7, 5, 0, 9, 8, 3, 4, 2, 6),
    (6, 1, 2, 3, 0, 4, 5, 9, 7, 8),
    (3, 6, 7, 4, 2, 0, 9, 5, 8, 1),
    (5, 8, 6, 9, 7, 2, 0, 1, 3, 4),
    (8, 9, 4, 5, 3, 6, 2, 0, 1, 7),
    (9, 4, 3, 8, 6, 1, 7, 2, 0, 5),
    (2, 5, 8, 1, 4, 3, 6, 7, 9, 0),
)


def fahrenheit_to_millic(fahrenheit: float) -> int:
    """Convert degrees Fahrenheit to June's milli-Celsius wire unit."""
    return round((fahrenheit - 32) * 5 / 9 * 1000)


def millic_to_celsius(millic: int | float) -> float:
    """Convert June's milli-Celsius wire unit to degrees Celsius."""
    return float(millic) / 1000


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert degrees Celsius to degrees Fahrenheit."""
    return celsius * 9 / 5 + 32


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert degrees Fahrenheit to degrees Celsius."""
    return (fahrenheit - 32) * 5 / 9


def damm(input_value: str) -> int:
    """Return the Damm checksum digit for a decimal string."""
    if not input_value.isdigit():
        raise ValueError("Damm input must contain only decimal digits")
    state = 0
    for character in input_value:
        state = DAMM[state][int(character)]
    return state


def build_shown_code(server_code: str, two_digits: int | None = None) -> str:
    """Build the eight-digit PIN displayed to the user."""
    if len(server_code) != 5 or not server_code.isdigit():
        raise ValueError("June pairing server code must contain five digits")
    suffix = secrets.randbelow(100) if two_digits is None else two_digits
    if not 0 <= suffix <= 99:
        raise ValueError("Pairing-code suffix must be between 0 and 99")
    base = f"{server_code}{suffix:02d}"
    return f"{base}{damm(base)}"


class OrderGenerator:
    """Generate strictly increasing message order values."""

    def __init__(self) -> None:
        self._last = 0

    def next(self, now_ms: int | None = None) -> int:
        """Return the next order number."""
        raw = int(time.time() * 1000) if now_ms is None else now_ms
        order = raw & 0x7FFFFFFF
        if order <= self._last:
            order = self._last + 1
        self._last = order
        return order


def build_signed_frame(
    identity: Mapping[str, str],
    message_code: int,
    data: Mapping[str, Any],
    order: int,
    now_ms: int | None = None,
) -> str:
    """Build the exact compact, signed JSON frame accepted by a June oven."""
    from nacl.signing import SigningKey

    timestamp = int(time.time() * 1000) if now_ms is None else now_ms
    message: dict[str, Any] = {
        "v": 2,
        "message_code": message_code,
        "order": order,
        "time": timestamp,
        "signature": "",
        "device_name": identity["device_name"],
        "device_id": identity["device_id"],
        "data": dict(data),
        "target": {"id": identity["oven_id"]},
    }
    payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode()
    signing_key = SigningKey(bytes.fromhex(identity["ed25519_seed_hex"]))
    public_key = signing_key.verify_key.encode()
    fingerprint = hashlib.blake2b(public_key, digest_size=8).digest()
    signature = signing_key.sign(payload).signature
    message["signature"] = base64.b64encode(fingerprint + signature).decode()
    return json.dumps(message, separators=(",", ":"), ensure_ascii=False)


def find_long_base64(value: Any) -> str | None:
    """Find the oven's long SRP public value in a pairing payload."""
    match = re.search(r'"([A-Za-z0-9+/=]{300,})"', json.dumps(value))
    return match.group(1) if match else None


def _sha1(*chunks: bytes) -> bytes:
    digest = hashlib.sha1()
    for chunk in chunks:
        digest.update(chunk)
    return digest.digest()


def _int_to_bytes(value: int, minimum_length: int = 0) -> bytes:
    if value < 0:
        raise ValueError("Cannot serialize a negative integer")
    raw_length = max(1, (value.bit_length() + 7) // 8)
    return value.to_bytes(max(raw_length, minimum_length), "big")


def _pad(value: int) -> bytes:
    return _int_to_bytes(value, SRP_PAD_LEN)


class SrpServer:
    """BouncyCastle-compatible SRP-6a server used during June pairing."""

    def __init__(
        self,
        password: str,
        *,
        salt: bytes | None = None,
        secret_b: int | None = None,
    ) -> None:
        self.salt = secrets.token_bytes(16) if salt is None else salt
        identity_hash = _sha1(f"user:{password}".encode())
        x = int.from_bytes(_sha1(self.salt, identity_hash), "big")
        verifier = pow(SRP_G, x, SRP_N)
        multiplier = int.from_bytes(_sha1(_pad(SRP_N), _pad(SRP_G)), "big")
        self._secret_b = (
            int.from_bytes(secrets.token_bytes(32), "big") % SRP_N
            if secret_b is None
            else secret_b % SRP_N
        )
        self.public_b = (
            multiplier * verifier + pow(SRP_G, self._secret_b, SRP_N)
        ) % SRP_N
        self._verifier = verifier

    @property
    def salt_base64(self) -> str:
        """Return the salt encoded for the June API."""
        return base64.b64encode(self.salt).decode()

    @property
    def public_base64(self) -> str:
        """Return the minimal unsigned encoding of public B."""
        return base64.b64encode(_int_to_bytes(self.public_b)).decode()

    def calculate_secret(self, public_a_base64: str) -> bytes:
        """Calculate the shared SRP secret from the oven's public A."""
        public_a = int.from_bytes(base64.b64decode(public_a_base64), "big")
        if public_a % SRP_N == 0:
            raise ValueError("Invalid SRP public value")
        scrambling = int.from_bytes(_sha1(_pad(public_a), _pad(self.public_b)), "big")
        secret = pow(
            (public_a * pow(self._verifier, scrambling, SRP_N)) % SRP_N,
            self._secret_b,
            SRP_N,
        )
        return _int_to_bytes(secret)
