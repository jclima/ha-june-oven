"""Asynchronous client and pairing flow for June ovens."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

from aiohttp import (
    ClientError,
    ClientResponse,
    ClientSession,
    ClientWebSocketResponse,
    WSMsgType,
    WSServerHandshakeError,
)

from .protocol import (
    JUNE_API_URL,
    JUNE_APP_VERSION,
    JUNE_CLIENT_ID,
    JUNE_CLIENT_SECRET,
    JUNE_MESSAGING_URL,
    JUNE_PLATFORM_VERSION,
    JUNE_USER_AGENT,
    JUNE_WS_URL,
    MC_ACK,
    MC_CAMERA,
    MC_CANCEL,
    MC_CANCELLED,
    MC_DEVICE_STATE,
    MC_KEEPALIVE,
    MC_PAIRING_INFO,
    MC_PAIRING_INVALIDATED,
    MC_PLAN,
    MC_PREHEAT,
    MC_SET_TIMER,
    MC_TELEMETRY,
    MC_TEMPERATURE,
    OrderGenerator,
    SrpServer,
    build_shown_code,
    build_signed_frame,
    fahrenheit_to_millic,
    find_long_base64,
    millic_to_celsius,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
COMMAND_TIMEOUT = 6
PAIRING_TIMEOUT = 5 * 60
TRIGGER_PULSE_SECONDS = 30
TRUSTED_CAMERA_HOSTS = {"api.junelife.com", "june-api.s3.amazonaws.com"}


class JuneError(Exception):
    """Base error for the June API."""


class JuneAuthenticationError(JuneError):
    """June rejected the companion credentials."""


class JuneConnectionError(JuneError):
    """June's cloud could not be reached."""


class JuneCommandError(JuneError):
    """The oven rejected or did not acknowledge a command."""


class JunePairingNotReady(JuneError):
    """The oven has not finished pairing yet."""


@dataclass(slots=True)
class JuneIdentity:
    """Persistent per-oven companion identity."""

    oven_id: str
    device_id: str
    device_name: str
    password: str
    ed25519_seed_hex: str
    access_token: str
    refresh_token: str
    client_id: str = JUNE_CLIENT_ID
    client_secret: str = JUNE_CLIENT_SECRET

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> JuneIdentity:
        """Construct an identity from config-entry data."""
        return cls(
            oven_id=str(data["oven_id"]),
            device_id=str(data["device_id"]),
            device_name=str(data["device_name"]),
            password=str(data["password"]),
            ed25519_seed_hex=str(data["ed25519_seed_hex"]),
            access_token=str(data.get("access_token", "")),
            refresh_token=str(data.get("refresh_token", "")),
            client_id=str(data.get("client_id", JUNE_CLIENT_ID)),
            client_secret=str(data.get("client_secret", JUNE_CLIENT_SECRET)),
        )

    def as_dict(self) -> dict[str, str]:
        """Return serializable config-entry data."""
        return asdict(self)


@dataclass(slots=True)
class JuneState:
    """Latest state retained in memory for Home Assistant entities."""

    connection_state: str = "unknown"
    active: bool = False
    current_temp_c: float | None = None
    target_temp_c: float | None = None
    cook_mode: str = "bake"
    progress_percent: float | None = None
    probe_temp_c: float | None = None
    probe_present: bool | None = None
    ready: bool = False
    done: bool = False
    snapshot_url: str | None = None
    last_ack_status: str | None = None

    @property
    def online(self) -> bool:
        """Return whether June reports the oven online."""
        return self.connection_state == "online"


TokenCallback = Callable[[JuneIdentity], None]
UpdateCallback = Callable[[JuneState], None]


class JuneClient:
    """Long-lived June cloud client."""

    def __init__(
        self,
        session: ClientSession,
        identity: JuneIdentity,
        *,
        token_callback: TokenCallback | None = None,
        update_callback: UpdateCallback | None = None,
    ) -> None:
        self.session = session
        self.identity = identity
        self.state = JuneState()
        self.token_callback = token_callback
        self.update_callback = update_callback
        self._orders = OrderGenerator()
        self._ws: ClientWebSocketResponse | None = None
        self._ws_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._pulse_tasks: dict[str, asyncio.Task[None]] = {}
        self._pending: dict[int, asyncio.Future[str | None]] = {}
        self._connected = asyncio.Event()
        self._stopped = False
        self._last_active = False
        self._last_cancelled = False
        self._command_lock = asyncio.Lock()

    def set_update_callback(self, callback: UpdateCallback) -> None:
        """Set the callback used for push updates."""
        self.update_callback = callback

    async def async_refresh_token(self) -> None:
        """Mint a fresh seven-day bearer token by re-registering the device."""
        body = {
            "password": self.identity.password,
            "device_id": self.identity.device_id,
            "client_id": self.identity.client_id,
            "client_secret": self.identity.client_secret,
            "device_type": "companion",
            "device_name": self.identity.device_name,
            "platform": "android",
            "version": JUNE_APP_VERSION,
            "platform_version": JUNE_PLATFORM_VERSION,
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self.session.post(
                    f"{JUNE_API_URL}/2/devices/register",
                    json=body,
                    headers={"User-Agent": JUNE_USER_AGENT},
                ) as response:
                    payload = await self._checked_json(response, "Token refresh")
        except JuneError:
            raise
        except (TimeoutError, ClientError) as err:
            raise JuneConnectionError(f"Token refresh failed: {err}") from err

        token = payload.get("token")
        if not isinstance(token, dict) or not isinstance(
            token.get("access_token"), str
        ):
            raise JuneError("June returned an invalid token response")
        self.identity.access_token = token["access_token"]
        refresh_token = token.get("refresh_token")
        if isinstance(refresh_token, str):
            self.identity.refresh_token = refresh_token
        if self.token_callback:
            self.token_callback(self.identity)

    async def async_fetch_status(self, *, retry_auth: bool = True) -> JuneState:
        """Fetch the oven's REST status snapshot."""
        url = f"{JUNE_MESSAGING_URL}/1/messaging/device/{self.identity.oven_id}/status"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self.session.get(
                    url, headers=self._authorization_headers()
                ) as response:
                    if response.status == 401 and retry_auth:
                        response.release()
                        await self.async_refresh_token()
                        return await self.async_fetch_status(retry_auth=False)
                    payload = await self._checked_json(response, "Status")
        except JuneError:
            raise
        except (TimeoutError, ClientError) as err:
            raise JuneConnectionError(f"Status failed: {err}") from err

        self._apply_status(payload)
        self._notify()
        return self.state

    def async_start_websocket(self) -> None:
        """Start the persistent messaging connection."""
        if self._ws_task and not self._ws_task.done():
            return
        self._stopped = False
        self._ws_task = asyncio.create_task(
            self._websocket_runner(), name="june-oven-websocket"
        )

    async def async_stop(self) -> None:
        """Stop background work and settle pending commands."""
        self._stopped = True
        self._connected.clear()
        tasks = [
            task
            for task in (
                self._keepalive_task,
                self._ws_task,
                *self._pulse_tasks.values(),
            )
            if task is not None
        ]
        for task in tasks:
            task.cancel()
        if self._ws is not None:
            await self._ws.close()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._ws = None
        self._ws_task = None
        self._keepalive_task = None
        self._pulse_tasks.clear()
        for future in self._pending.values():
            if not future.done():
                future.set_result(None)
        self._pending.clear()

    async def async_preheat(self, mode: str, temperature_f: float) -> None:
        """Start a cook/preheat and require a success acknowledgement."""
        self._last_cancelled = False
        status = await self._async_send_command(
            MC_PREHEAT,
            {
                "primitive_type": mode,
                "temperature_cavity": fahrenheit_to_millic(temperature_f),
            },
        )
        self._require_success(status, "start cook")
        self.state.cook_mode = mode
        self.state.target_temp_c = (temperature_f - 32) * 5 / 9
        self.state.done = False
        self._notify()

    async def async_cancel(self) -> None:
        """Cancel the active cook."""
        self._last_cancelled = True
        status = await self._async_send_command(MC_CANCEL, {"plan_id": 0})
        if status not in ("success", "not-allowed"):
            self._last_cancelled = False
            self._require_success(status, "cancel cook")

    async def async_set_target_f(self, temperature_f: float, mode: str) -> None:
        """Set a target, restarting an active cook when necessary."""
        self.state.target_temp_c = (temperature_f - 32) * 5 / 9
        self._notify()
        if not self.state.active:
            return
        await self.async_cancel()
        await asyncio.sleep(0.4)
        await self.async_preheat(mode, temperature_f)

    async def async_set_mode(self, mode: str, temperature_f: float) -> None:
        """Select a cook mode, restarting an active cook if needed."""
        self.state.cook_mode = mode
        self._notify()
        if not self.state.active:
            return
        await self.async_cancel()
        await asyncio.sleep(0.4)
        await self.async_preheat(mode, temperature_f)

    async def async_set_timer(self, minutes: float) -> None:
        """Set the oven's native cook timer."""
        status = await self._async_send_command(
            MC_SET_TIMER,
            {"plan_id": 0, "duration": round(minutes * 60_000)},
        )
        self._require_success(status, "set timer")

    async def async_fetch_camera_image(self) -> bytes | None:
        """Fetch the most recent trusted camera image."""
        url = self.state.snapshot_url
        if not url or not self._is_trusted_camera_url(url):
            return None
        try:
            async with asyncio.timeout(8):
                async with self.session.get(url, allow_redirects=False) as response:
                    if response.status != 200:
                        return None
                    try:
                        content_length = int(
                            response.headers.get("Content-Length", "0")
                        )
                    except ValueError:
                        content_length = 0
                    if content_length > 10 * 1024 * 1024:
                        raise JuneError("June camera response is too large")
                    image = await response.read()
                    if len(image) > 10 * 1024 * 1024:
                        raise JuneError("June camera response is too large")
                    return image
        except (TimeoutError, ClientError) as err:
            _LOGGER.debug("Camera image fetch failed: %s", err)
            return None

    async def _websocket_runner(self) -> None:
        attempt = 0
        while not self._stopped:
            try:
                await self._websocket_once()
                attempt = 0
            except asyncio.CancelledError:
                raise
            except WSServerHandshakeError as err:
                if err.status == 401:
                    try:
                        await self.async_refresh_token()
                    except JuneError as refresh_err:
                        _LOGGER.warning("June token renewal failed: %s", refresh_err)
                else:
                    _LOGGER.debug("June WebSocket handshake failed: %s", err)
            except (ClientError, JuneError) as err:
                _LOGGER.debug("June WebSocket disconnected: %s", err)
            finally:
                self._connected.clear()
                self._ws = None
                if self._keepalive_task:
                    self._keepalive_task.cancel()
                    await asyncio.gather(self._keepalive_task, return_exceptions=True)
                    self._keepalive_task = None
            if self._stopped:
                break
            attempt += 1
            delay = min(120, 2 ** min(attempt - 1, 7))
            await asyncio.sleep(delay)

    async def _websocket_once(self) -> None:
        async with self.session.ws_connect(
            JUNE_WS_URL,
            headers={
                **self._authorization_headers(),
                "User-Agent": JUNE_USER_AGENT,
            },
            heartbeat=20,
            compress=0,
        ) as websocket:
            self._ws = websocket
            self._connected.set()
            self._keepalive_task = asyncio.create_task(
                self._keepalive_loop(), name="june-oven-keepalive"
            )
            async for message in websocket:
                if message.type == WSMsgType.TEXT:
                    self._handle_message(message.data)
                elif message.type in (
                    WSMsgType.CLOSE,
                    WSMsgType.CLOSED,
                    WSMsgType.ERROR,
                ):
                    break

    async def _keepalive_loop(self) -> None:
        while not self._stopped:
            try:
                await self._async_send_frame(MC_KEEPALIVE, {})
            except JuneError:
                return
            await asyncio.sleep(7)

    async def _async_send_frame(
        self,
        code: int,
        data: Mapping[str, Any],
        *,
        expect_ack: bool = False,
    ) -> tuple[int, asyncio.Future[str | None] | None]:
        try:
            async with asyncio.timeout(15):
                await self._connected.wait()
        except TimeoutError as err:
            raise JuneConnectionError("June messaging socket is not connected") from err
        websocket = self._ws
        if websocket is None or websocket.closed:
            raise JuneConnectionError("June messaging socket is not connected")
        order = self._orders.next()
        frame = build_signed_frame(self.identity.as_dict(), code, data, order)
        future: asyncio.Future[str | None] | None = None
        if expect_ack:
            future = asyncio.get_running_loop().create_future()
            self._pending[order] = future
        try:
            await websocket.send_str(frame)
        except Exception:
            self._pending.pop(order, None)
            raise
        return order, future

    async def _async_send_command(
        self, code: int, data: Mapping[str, Any]
    ) -> str | None:
        async with self._command_lock:
            order, future = await self._async_send_frame(code, data, expect_ack=True)
            assert future is not None
            try:
                async with asyncio.timeout(COMMAND_TIMEOUT):
                    return await future
            except TimeoutError:
                return None
            finally:
                self._pending.pop(order, None)

    def _handle_message(self, raw_message: str) -> None:
        try:
            frame = json.loads(raw_message)
        except json.JSONDecodeError:
            return
        if not isinstance(frame, dict):
            return
        code = frame.get("message_code")
        data = frame.get("data")
        if not isinstance(data, dict):
            data = {}

        if code == MC_ACK and isinstance(data.get("request_order"), int):
            future = self._pending.get(data["request_order"])
            if future and not future.done():
                status = data.get("status")
                self.state.last_ack_status = status if isinstance(status, str) else None
                future.set_result(self.state.last_ack_status)
            return

        if code == MC_TELEMETRY:
            self._apply_telemetry(data)
        elif code == MC_CAMERA:
            candidate = data.get("image_url") or data.get("signed_url")
            if self._is_trusted_camera_url(candidate):
                self.state.snapshot_url = candidate
        elif code in (MC_PLAN, MC_TEMPERATURE):
            target = self._find_temperature(data)
            if target is not None:
                self.state.target_temp_c = millic_to_celsius(target)
            food = data.get("food")
            if isinstance(food, dict) and isinstance(food.get("name"), str):
                self.state.cook_mode = food["name"]
        elif code == MC_CANCELLED and data.get("type") == "cancelled":
            self._last_cancelled = True
        elif code == MC_DEVICE_STATE:
            self._apply_active(data.get("state") == "active")
        else:
            return
        self._notify()

    def _apply_status(self, payload: Mapping[str, Any]) -> None:
        connection = payload.get("connection_state")
        if isinstance(connection, str):
            self.state.connection_state = connection
        device_state = payload.get("device_state")
        if isinstance(device_state, dict):
            state_data = device_state.get("data")
            if isinstance(state_data, dict):
                self._apply_active(state_data.get("state") == "active")
        cook_plan = payload.get("cook_plan")
        if isinstance(cook_plan, dict):
            plan_data = cook_plan.get("data")
            if isinstance(plan_data, dict):
                target = self._find_temperature(plan_data)
                if target is not None:
                    self.state.target_temp_c = millic_to_celsius(target)
                food = plan_data.get("food")
                if isinstance(food, dict) and isinstance(food.get("name"), str):
                    self.state.cook_mode = food["name"]

    def _apply_telemetry(self, data: Mapping[str, Any]) -> None:
        sensor_data = data.get("sensor_data")
        if isinstance(sensor_data, dict):
            cavity = sensor_data.get("cavity")
            if isinstance(cavity, (int, float)):
                self.state.current_temp_c = millic_to_celsius(cavity)
            probe = sensor_data.get("probe")
            if isinstance(probe, list):
                self.state.probe_present = bool(probe)
                reading = next(
                    (
                        entry.get("value")
                        for entry in probe
                        if isinstance(entry, dict)
                        and isinstance(entry.get("value"), (int, float))
                    ),
                    None,
                )
                self.state.probe_temp_c = (
                    millic_to_celsius(reading) if reading is not None else None
                )

        cook_state = data.get("cook_state_data")
        if isinstance(cook_state, dict):
            progress = cook_state.get("progress")
            if isinstance(progress, (int, float)):
                normalized = float(progress)
                self.state.progress_percent = (
                    normalized * 100 if normalized <= 1 else normalized
                )
                is_ready = (
                    normalized >= 0.995
                    and self.state.current_temp_c is not None
                    and self.state.target_temp_c is not None
                    and self.state.current_temp_c + 0.6 >= self.state.target_temp_c
                )
                if is_ready and not self.state.ready:
                    self._start_pulse("ready")

    def _apply_active(self, active: bool) -> None:
        if self._last_active and not active and not self._last_cancelled:
            self._start_pulse("done")
        self.state.active = active
        self._last_active = active
        if active:
            self._last_cancelled = False
            self.state.done = False
            self.state.ready = False

    def _start_pulse(self, field: str) -> None:
        setattr(self.state, field, True)
        existing = self._pulse_tasks.get(field)
        if existing:
            existing.cancel()
        self._pulse_tasks[field] = asyncio.create_task(
            self._reset_pulse(field), name=f"june-oven-{field}-pulse"
        )

    async def _reset_pulse(self, field: str) -> None:
        try:
            await asyncio.sleep(TRIGGER_PULSE_SECONDS)
            setattr(self.state, field, False)
            self._notify()
        except asyncio.CancelledError:
            raise
        finally:
            if self._pulse_tasks.get(field) is asyncio.current_task():
                self._pulse_tasks.pop(field, None)

    def _notify(self) -> None:
        if self.update_callback:
            self.update_callback(self.state)

    def _authorization_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.identity.access_token}"}

    @staticmethod
    async def _checked_json(response: ClientResponse, operation: str) -> dict[str, Any]:
        if response.status == 401:
            raise JuneAuthenticationError(f"{operation}: unauthorized")
        if response.status < 200 or response.status >= 300:
            await response.read()
            raise JuneError(f"{operation} failed with HTTP {response.status}")
        payload = await response.json(content_type=None)
        if not isinstance(payload, dict):
            raise JuneError(f"{operation} returned invalid JSON")
        return payload

    @staticmethod
    def _require_success(status: str | None, operation: str) -> None:
        if status != "success":
            raise JuneCommandError(
                f"June could not {operation}: {status or 'no acknowledgement'}"
            )

    @staticmethod
    def _find_temperature(value: Any) -> int | float | None:
        if isinstance(value, dict):
            direct = value.get("temperature_cavity")
            if isinstance(direct, (int, float)):
                return direct
            for child in value.values():
                found = JuneClient._find_temperature(child)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = JuneClient._find_temperature(child)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _is_trusted_camera_url(candidate: Any) -> bool:
        if not isinstance(candidate, str):
            return False
        parsed = urlparse(candidate)
        return parsed.scheme == "https" and parsed.hostname in TRUSTED_CAMERA_HOSTS


class JunePairingSession:
    """One self-contained PIN pairing session."""

    def __init__(
        self,
        session: ClientSession,
        device_name: str,
        timezone: str = "UTC",
    ) -> None:
        self.session = session
        self.device_name = device_name
        self.timezone = timezone
        self.shown_code: str | None = None
        self.identity: JuneIdentity | None = None
        self.error: JuneError | None = None
        self._registration: dict[str, str] | None = None
        self._server_code: str | None = None
        self._srp: SrpServer | None = None
        self._signing_key: Any = None
        self._encryption_key: Any = None
        self._ws: ClientWebSocketResponse | None = None
        self._listen_task: asyncio.Task[None] | None = None
        self._completion_task: asyncio.Task[None] | None = None
        self._deadline_task: asyncio.Task[None] | None = None
        self._finished = asyncio.Event()

    async def async_begin(self) -> str:
        """Register a companion, open messaging, and return the display PIN."""
        from nacl.public import PrivateKey
        from nacl.signing import SigningKey

        self._registration = await self._async_register_device()
        self._signing_key = SigningKey.generate()
        self._encryption_key = PrivateKey.generate()
        try:
            self._ws = await self.session.ws_connect(
                JUNE_WS_URL,
                headers={
                    "Authorization": (f"Bearer {self._registration['access_token']}"),
                    "User-Agent": JUNE_USER_AGENT,
                },
                heartbeat=20,
                compress=0,
            )
        except (TimeoutError, ClientError) as err:
            raise JuneConnectionError(
                f"Could not open June pairing socket: {err}"
            ) from err
        self._listen_task = asyncio.create_task(
            self._async_listen(), name="june-oven-pairing-listener"
        )
        try:
            self._server_code = await self._async_request_pairing_code()
            self.shown_code = build_shown_code(self._server_code)
            self._srp = SrpServer(self.shown_code)
            self._deadline_task = asyncio.create_task(
                self._async_deadline(), name="june-oven-pairing-timeout"
            )
        except Exception:
            await self.async_close()
            raise
        return self.shown_code

    async def async_wait_paired(self, wait_seconds: float = 12) -> JuneIdentity:
        """Wait briefly for pairing, allowing a config flow to retry."""
        try:
            async with asyncio.timeout(wait_seconds):
                await self._finished.wait()
        except TimeoutError as err:
            raise JunePairingNotReady("The oven has not finished pairing yet") from err
        if self.error:
            raise self.error
        if not self.identity:
            raise JunePairingNotReady("The oven has not finished pairing yet")
        return self.identity

    async def async_close(self) -> None:
        """Close sockets and background tasks."""
        current = asyncio.current_task()
        tasks = [
            task
            for task in (
                self._listen_task,
                self._completion_task,
                self._deadline_task,
            )
            if task is not None and task is not current
        ]
        for task in tasks:
            task.cancel()
        if self._ws is not None:
            await self._ws.close()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._ws = None

    async def _async_register_device(self) -> dict[str, str]:
        device_id = secrets.token_hex(16)
        password = secrets.token_hex(16)
        body = {
            "password": password,
            "device_id": device_id,
            "client_id": JUNE_CLIENT_ID,
            "client_secret": JUNE_CLIENT_SECRET,
            "device_type": "companion",
            "device_name": self.device_name,
            "platform": "android",
            "version": JUNE_APP_VERSION,
            "platform_version": JUNE_PLATFORM_VERSION,
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self.session.post(
                    f"{JUNE_API_URL}/2/devices/register",
                    json=body,
                    headers={"User-Agent": JUNE_USER_AGENT},
                ) as response:
                    payload = await JuneClient._checked_json(
                        response, "Device registration"
                    )
        except JuneError:
            raise
        except (TimeoutError, ClientError) as err:
            raise JuneConnectionError(f"Device registration failed: {err}") from err
        token = payload.get("token")
        if not isinstance(token, dict) or not isinstance(
            token.get("access_token"), str
        ):
            raise JuneError("June returned an invalid registration response")
        return {
            "device_id": device_id,
            "password": password,
            "access_token": token["access_token"],
            "refresh_token": str(token.get("refresh_token", "")),
        }

    async def _async_request_pairing_code(self) -> str:
        assert self._registration is not None
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self.session.post(
                    f"{JUNE_API_URL}/2/devices/pairing",
                    headers={
                        "Authorization": (
                            f"Bearer {self._registration['access_token']}"
                        ),
                        "User-Agent": JUNE_USER_AGENT,
                    },
                ) as response:
                    payload = await JuneClient._checked_json(
                        response, "Pairing-code request"
                    )
        except JuneError:
            raise
        except (TimeoutError, ClientError) as err:
            raise JuneConnectionError(f"Pairing-code request failed: {err}") from err
        pin = payload.get("pin")
        if not isinstance(pin, dict) or not isinstance(pin.get("code"), str):
            raise JuneError("June returned an invalid pairing code")
        return pin["code"]

    async def _async_listen(self) -> None:
        assert self._ws is not None
        try:
            async for message in self._ws:
                if message.type != WSMsgType.TEXT:
                    continue
                try:
                    frame = json.loads(message.data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(frame, dict):
                    continue
                if frame.get("message_code") == MC_PAIRING_INVALIDATED:
                    self._fail(
                        JuneError(
                            "The oven invalidated pairing. Confirm it is "
                            "idle, closed, online, and retry."
                        )
                    )
                    return
                if (
                    frame.get("message_code") == MC_PAIRING_INFO
                    and self._completion_task is None
                ):
                    public_a = find_long_base64(frame.get("data"))
                    if public_a:
                        self._completion_task = asyncio.create_task(
                            self._async_complete_pairing(public_a),
                            name="june-oven-pairing-completion",
                        )
        except asyncio.CancelledError:
            raise
        except (ClientError, JuneError) as err:
            self._fail(JuneConnectionError(f"Pairing socket failed: {err}"))

    async def _async_complete_pairing(self, public_a: str) -> None:
        from nacl.secret import SecretBox

        assert self._registration is not None
        assert self._server_code is not None
        assert self._srp is not None
        try:
            secret = self._srp.calculate_secret(public_a)
            key = hashlib.blake2b(secret, digest_size=32).digest()
            signing_public = self._signing_key.verify_key.encode()
            encryption_public = bytes(self._encryption_key.public_key)
            companion_info = {
                "companion_id": self._registration["device_id"],
                "companion_name": self.device_name,
                "public_signing_key": base64.b64encode(signing_public).decode(),
                "public_encryption_key": base64.b64encode(encryption_public).decode(),
                "timezone": self.timezone,
                "platform": "Android",
            }
            nonce = secrets.token_bytes(24)
            encrypted = bytes(
                SecretBox(key).encrypt(
                    json.dumps(companion_info, separators=(",", ":")).encode(),
                    nonce,
                )
            )
            body = {
                "key_info": {
                    "salt": self._srp.salt_base64,
                    "B": self._srp.public_base64,
                    "companion_info": base64.b64encode(encrypted).decode(),
                }
            }
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self.session.post(
                    (f"{JUNE_API_URL}/2/devices/pairing/{self._server_code}/companion"),
                    json=body,
                    headers={
                        "Authorization": (
                            f"Bearer {self._registration['access_token']}"
                        ),
                        "User-Agent": JUNE_USER_AGENT,
                    },
                ) as response:
                    await JuneClient._checked_json(
                        response, "Companion key registration"
                    )
            await self._async_wait_for_association()
        except asyncio.CancelledError:
            raise
        except JuneError as err:
            self._fail(err)
        except (TimeoutError, ClientError, ValueError) as err:
            self._fail(JuneConnectionError(f"Pairing failed: {err}"))

    async def _async_wait_for_association(self) -> None:
        assert self._registration is not None
        for attempt in range(20):
            await asyncio.sleep(min(30, 3 * (2 ** min(attempt, 4))))
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    async with self.session.get(
                        (
                            f"{JUNE_API_URL}/2/devices/"
                            f"{self._registration['device_id']}/associated"
                        ),
                        headers={
                            "Authorization": (
                                f"Bearer {self._registration['access_token']}"
                            ),
                            "User-Agent": JUNE_USER_AGENT,
                        },
                    ) as response:
                        if response.status >= 500 or response.status == 429:
                            await response.read()
                            continue
                        payload = await JuneClient._checked_json(
                            response, "Association status"
                        )
            except (TimeoutError, ClientError):
                continue
            devices = payload.get("devices")
            if not isinstance(devices, list):
                continue
            oven = next(
                (
                    device
                    for device in devices
                    if isinstance(device, dict)
                    and isinstance(device.get("oven_id"), str)
                ),
                None,
            )
            if not oven:
                continue
            self.identity = JuneIdentity(
                oven_id=oven["oven_id"],
                device_id=self._registration["device_id"],
                device_name=self.device_name,
                password=self._registration["password"],
                ed25519_seed_hex=bytes(self._signing_key).hex(),
                access_token=self._registration["access_token"],
                refresh_token=self._registration["refresh_token"],
            )
            self._finished.set()
            await self.async_close()
            return
        self._fail(
            JunePairingNotReady("Timed out waiting for the oven to finish pairing")
        )

    async def _async_deadline(self) -> None:
        await asyncio.sleep(PAIRING_TIMEOUT)
        self._fail(JunePairingNotReady("Pairing session timed out"))
        await self.async_close()

    def _fail(self, error: JuneError) -> None:
        if self._finished.is_set():
            return
        self.error = error
        self._finished.set()
        asyncio.create_task(self.async_close(), name="june-oven-pairing-cleanup")
