"""June cloud wire-protocol helpers.

Ported from the MIT-licensed homebridge-june-oven project. These helpers have
no Home Assistant dependency so their serialization and math can be tested in
isolation.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit

JUNE_API_URL: Final = "https://api.junelife.com"
JUNE_MESSAGING_URL: Final = "https://messaging.junelife.com"
JUNE_WS_PATH: Final = "/1/messaging/websocket/companion"
JUNE_WS_URL: Final = f"wss://messaging.junelife.com{JUNE_WS_PATH}"
JUNE_USER_AGENT: Final = "okhttp/4.8.1"
JUNE_APP_VERSION: Final = "1.24.1.11"
JUNE_PLATFORM_VERSION: Final = "34"

# Constants embedded in the official June Android application. They identify
# the application, not a user's June account or oven.
JUNE_CLIENT_ID: Final = "dcxqbcv2dY-G12elqDoAhCP8E12V0zC8XWThT-4U"
JUNE_CLIENT_SECRET: Final = "tmoSUwt3OOZCcfMaIadAGD7-x-qPht85HkCgdvuhTKk1yFtfMcfJEyd"

MC_PREHEAT: Final = 11002
MC_CANCEL: Final = 11004
MC_SET_TEMPERATURE: Final = 11005
MC_SET_TIMER: Final = 11006
MC_KEEPALIVE: Final = 11011

MC_CAMERA: Final = 10011
MC_NOTIFICATION: Final = 10012
MC_TELEMETRY: Final = 10013
MC_PLAN_STARTED: Final = 10014
MC_PLAN: Final = 10015
MC_TEMPERATURE: Final = 10016
MC_CANCELLED: Final = 10017
MC_DEVICE_STATE: Final = 10018
MC_ACK: Final = 10020
MC_PAIRING_INFO: Final = 10026
MC_PAIRING_INVALIDATED: Final = 10027

NOTIFICATION_PREHEAT_COMPLETE: Final = "NOTIFICATION_PREHEAT_COMPLETE"
# The cook-plan step the oven holds at temperature until food goes in.
PRESENTATION_PREHEAT: Final = "preheat"
PRESENTATION_PREHEAT_AND_HOLD: Final = "preheat_and_hold"
PRESENTATION_COOKING: Final = frozenset({"cook_bound", "cook_unbound"})

PHASE_IDLE: Final = "idle"
PHASE_PREHEATING: Final = "preheating"
PHASE_PREHEATED: Final = "preheated"
PHASE_COOKING: Final = "cooking"
COOK_PHASES: Final = (PHASE_IDLE, PHASE_PREHEATING, PHASE_PREHEATED, PHASE_COOKING)

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

# Project July's june-local server serves the same routes over TLS on 443 and
# over plain HTTP on this port.
LOCAL_HTTP_PORT: Final = 8080

_HOSTNAME = re.compile(
    r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
)


@dataclass(frozen=True, slots=True)
class JuneEndpoints:
    """Every URL the companion uses, derived from one configured endpoint."""

    api_url: str
    messaging_url: str
    ws_url: str
    local: bool

    @property
    def status_url(self) -> str:
        """Return the local server's machine-readable status URL."""
        return f"{self.api_url}/local/status"

    def local_media_url(self, candidate: Any) -> str | None:
        """Re-home a camera URL onto the configured local server.

        The local server names api.junelife.com (or its --media-url) in camera
        frames because the oven believes it is talking to June's cloud. Only the
        path is kept, so images are only ever fetched from the configured server.
        """
        if not self.local or not isinstance(candidate, str):
            return None
        parsed = urlsplit(candidate)
        if not parsed.path.startswith("/media/") or ".." in parsed.path.split("/"):
            return None
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{self.api_url}{parsed.path}{query}"


def normalize_endpoint(value: str) -> str:
    """Normalize a user-entered endpoint to ``scheme://host[:port]``.

    Accepts a hostname or an IPv4/IPv6 address, optionally with a port and an
    ``https://`` or ``http://`` prefix. HTTPS is assumed; plain HTTP defaults to
    the local server's port-8080 listener. An empty value returns "" and selects
    June's public cloud. Raises ValueError for anything else.
    """
    value = value.strip()
    if not value:
        return ""
    try:
        if ipaddress.ip_address(value).version == 6:
            value = f"[{value}]"
    except ValueError:
        pass
    if "://" not in value:
        value = f"https://{value}"

    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Unsupported scheme: {parsed.scheme}")
    if parsed.username or parsed.password or parsed.path.strip("/"):
        raise ValueError("Enter only a hostname or IP address and optional port")
    host = parsed.hostname
    port = parsed.port  # Raises ValueError for a malformed port.
    if not host:
        raise ValueError("Missing hostname")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        host = host.rstrip(".")
        if not _HOSTNAME.fullmatch(host):
            raise ValueError(f"Invalid hostname: {host}") from None
    else:
        host = f"[{address.compressed}]" if address.version == 6 else str(address)

    if scheme == "http" and port is None:
        port = LOCAL_HTTP_PORT
    if scheme == "https" and port == 443:
        port = None
    return f"{scheme}://{host}" + (f":{port}" if port is not None else "")


def build_endpoints(endpoint: str = "") -> JuneEndpoints:
    """Derive every service URL from one endpoint; empty means June's cloud."""
    base = normalize_endpoint(endpoint)
    if not base:
        return JuneEndpoints(
            api_url=JUNE_API_URL,
            messaging_url=JUNE_MESSAGING_URL,
            ws_url=JUNE_WS_URL,
            local=False,
        )
    scheme, _, netloc = base.partition("://")
    ws_scheme = "wss" if scheme == "https" else "ws"
    return JuneEndpoints(
        api_url=base,
        messaging_url=base,
        ws_url=f"{ws_scheme}://{netloc}{JUNE_WS_PATH}",
        local=True,
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


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


@dataclass(frozen=True, slots=True)
class CookPlan:
    """The parts of an oven cook plan the integration tracks."""

    plan_id: int | None
    name: str | None
    session_id: str | None
    presentation_type: str | None
    target_millic: int | None


def parse_cook_plan(value: Any) -> CookPlan | None:
    """Parse a cook plan.

    Plans arrive as the data of 10014/10015/10016, as ``cook_plan_data`` in every
    10013, and as the REST status ``cook_plan``. The target and presentation come
    from the current step, ``food.plan.steps[step_state.step_index]``: after a
    temperature change the first step still holds the original target.
    """
    plan_data = _mapping(value)
    if plan_data is None:
        return None
    food = _mapping(plan_data.get("food"))
    if food is None:
        return None
    plan = _mapping(food.get("plan")) or {}
    steps = plan.get("steps")
    steps = steps if isinstance(steps, list) else []
    step_state = _mapping(plan_data.get("step_state"))
    index = _number(step_state.get("step_index")) if step_state else 0
    step: Mapping[str, Any] = {}
    if isinstance(index, int) and 0 <= index < len(steps):
        step = _mapping(steps[index]) or {}
    plan_id = _number(plan.get("id"))
    target = _number(step.get("temperature_cavity"))
    return CookPlan(
        plan_id=int(plan_id) if plan_id is not None else None,
        name=_string(food.get("name")),
        session_id=_string(plan_data.get("session_id")),
        presentation_type=_string(step.get("presentation_type")),
        target_millic=int(target) if target is not None and target > 0 else None,
    )


@dataclass(frozen=True, slots=True)
class CookProgress:
    """Progress reported in a 10013 ``cook_state_data``."""

    label_type: str | None
    percent: float | None
    elapsed_ms: int | None


def parse_cook_progress(value: Any) -> CookProgress | None:
    """Parse ``cook_state_data``.

    ``progress`` is ``{"label_type", "label_value", "percentage"}``. The
    percentage is already 0-100: 0.99 means 1% of the preheat gap is covered.
    ``label_type`` is "temperature" while preheating (``label_value`` is the
    cavity in milli-Celsius) and "time" while cooking (``label_value`` is the
    elapsed milliseconds, also sent as ``cook_time_elapsed``).
    """
    cook_state = _mapping(value)
    if cook_state is None:
        return None
    progress = _mapping(cook_state.get("progress")) or {}
    label_type = _string(progress.get("label_type"))
    percent = _number(progress.get("percentage"))
    elapsed = _number(cook_state.get("cook_time_elapsed"))
    if elapsed is None and label_type == "time":
        elapsed = _number(progress.get("label_value"))
    return CookProgress(
        label_type=label_type,
        percent=min(100.0, max(0.0, float(percent))) if percent is not None else None,
        elapsed_ms=int(elapsed) if elapsed is not None else None,
    )


def cook_phase(
    active: bool, presentation_type: str | None, label_type: str | None
) -> str:
    """Summarize what an active cook is doing."""
    if not active:
        return PHASE_IDLE
    if presentation_type == PRESENTATION_PREHEAT:
        return PHASE_PREHEATING
    if presentation_type == PRESENTATION_PREHEAT_AND_HOLD:
        return PHASE_PREHEATED
    if presentation_type not in PRESENTATION_COOKING and label_type == "temperature":
        return PHASE_PREHEATING
    return PHASE_COOKING


def connection_online(value: Any) -> bool | None:
    """Map a connection state to online, offline, or unknown."""
    if value in ("online", "connected"):
        return True
    if value in ("offline", "disconnected"):
        return False
    return None


def _unwrap(value: Any) -> Mapping[str, Any] | None:
    mapping = _mapping(value)
    if mapping is not None and _mapping(mapping.get("data")) is not None:
        return mapping["data"]
    return mapping


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    """A parsed REST status response."""

    online: bool | None
    device_state: str | None
    cook_plan: CookPlan | None


def parse_status(payload: Mapping[str, Any]) -> StatusSnapshot:
    """Parse ``/1/messaging/device/{id}/status``.

    june-local returns ``ha_connection_state`` "online"/"offline" beside
    ``connection_state`` "connected"/"disconnected", and the raw
    ``device_state`` and ``cook_plan`` beside ``{"data": ...}``-wrapped copies
    under ``device_state_data`` and ``cook_plan_data``. June's cloud sent only
    ``connection_state``, ``device_state`` and ``cook_plan``. The ``ha_`` and
    ``_data`` aliases win; any field may be wrapped or bare.
    """
    online = connection_online(payload.get("ha_connection_state"))
    if online is None:
        online = connection_online(payload.get("connection_state"))
    if online is None and isinstance(payload.get("online"), bool):
        online = payload["online"]
    device_state = None
    for key in ("device_state_data", "device_state"):
        device = _unwrap(payload.get(key))
        device_state = _string(device.get("state")) if device else None
        if device_state is not None:
            break
    cook_plan = parse_cook_plan(
        _unwrap(payload.get("cook_plan_data"))
    ) or parse_cook_plan(_unwrap(payload.get("cook_plan")))
    return StatusSnapshot(
        online=online,
        device_state=device_state,
        cook_plan=cook_plan,
    )


class PreheatWatch:
    """Decide when a cook has just finished preheating.

    The oven says so twice: the current step becomes preheat_and_hold, and it
    sends a 10012 NOTIFICATION_PREHEAT_COMPLETE. Frames are not strictly
    ordered (a 10015 can repeat the previous step after a 10016 moved on) and
    REST snapshots lag the socket, so each cook session fires at most once. A
    plan first seen already holding, such as after a restart, does not fire.
    """

    def __init__(self) -> None:
        self._session: str | None = None
        self._presentation: str | None = None
        self._fired: str | None = None

    def plan(self, plan: CookPlan) -> bool:
        """Track a cook plan; return True when preheating just finished."""
        if plan.session_id != self._session:
            self._session = plan.session_id
            self._presentation = None
        previous, self._presentation = self._presentation, plan.presentation_type
        if plan.presentation_type != PRESENTATION_PREHEAT_AND_HOLD or previous in (
            None,
            PRESENTATION_PREHEAT_AND_HOLD,
        ):
            return False
        return self._fire(plan.session_id)

    def notification(self, data: Mapping[str, Any]) -> bool:
        """Track a 10012; return True when preheating just finished."""
        if data.get("notification_id") != NOTIFICATION_PREHEAT_COMPLETE:
            return False
        return self._fire(_string(data.get("session_id")))

    def _fire(self, session: str | None) -> bool:
        if session is not None and session == self._fired:
            return False
        self._fired = session
        return True


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
