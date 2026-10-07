"""Client for the DOMO (Hududgaz) mobile gateway.

Kept free of Home Assistant imports so it can be tested on its own.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import secrets
import string
import time
import uuid
from collections.abc import Callable
from typing import Any

import aiohttp

BASE_URL = "https://domo-gw.uz/api/v1/"
APP_VERSION = "2.2.8"
PLATFORM = "ANDROID"
DEVICE_OS = "14"
DEVICE_MODEL = "Home Assistant"
TIMEOUT = aiohttp.ClientTimeout(total=30)

# Refresh the 7-day access token once it has less than a day left.
ACCESS_REFRESH_MARGIN = 24 * 3600


class DomoError(Exception):
    """Base error."""


class DomoConnectionError(DomoError):
    """Network failure or unexpected server response."""


class DomoAuthError(DomoError):
    """The refresh token was rejected: a new SMS login is needed."""


class DomoRequestError(DomoError):
    """The API rejected the request with a 4xx and a `detail` code."""

    def __init__(self, status: int, code: str, retry_after: int | None = None) -> None:
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code
        self.retry_after = retry_after


def new_device_id() -> str:
    return str(uuid.uuid4())


def new_client_secret() -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))


def normalize_phone(phone: str) -> str:
    """Return the phone as `+998XXXXXXXXX`, the format RequestOTP accepts."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) != 12 or not digits.startswith("998"):
        raise ValueError("invalid_phone")
    return "+" + digits


def jwt_claims(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return {}


def _detail(body: Any) -> str:
    """The gateway returns `{"detail": "code"}` or `{"detail": {"error": "code", ...}}`."""
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, dict):
            return str(detail.get("error") or detail.get("message") or detail)
    return "unknown_error"


class DomoClient:
    """Talks to the DOMO gateway as a registered device."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        device_id: str,
        client_secret: str,
        access: str | None = None,
        refresh: str | None = None,
        on_tokens: Callable[[str, str], None] | None = None,
        lang: str = "ru",
    ) -> None:
        self._session = session
        self.device_id = device_id
        self.client_secret = client_secret
        self.access = access
        self.refresh = refresh
        self._on_tokens = on_tokens
        self._lang = lang
        self._refresh_lock = asyncio.Lock()

    # -- low level -----------------------------------------------------------

    def _headers(self, auth: bool) -> dict[str, str]:
        headers = {
            "Device-Id": self.device_id,
            "Platform": PLATFORM,
            "Device-OS": DEVICE_OS,
            "Device-Model": DEVICE_MODEL,
            "Accept-Language": self._lang,
            "App-Version": APP_VERSION,
            "User-Agent": f"DOMO/{APP_VERSION} ({DEVICE_MODEL})",
        }
        if auth and self.access:
            headers["Authorization"] = f"Bearer {self.access}"
        return headers

    async def _send(
        self, method: str, path: str, payload: dict | None, auth: bool
    ) -> tuple[int, Any]:
        try:
            async with self._session.request(
                method,
                BASE_URL + path,
                json=payload,
                headers=self._headers(auth),
                timeout=TIMEOUT,
            ) as resp:
                try:
                    body = await resp.json(content_type=None)
                except ValueError:
                    body = None
                return resp.status, body
        except (aiohttp.ClientError, TimeoutError) as err:
            raise DomoConnectionError(str(err)) from err

    @staticmethod
    def _raise_for(status: int, body: Any) -> None:
        if 400 <= status < 500:
            retry_after = body.get("retry_after") if isinstance(body, dict) else None
            raise DomoRequestError(status, _detail(body), retry_after)
        raise DomoConnectionError(f"HTTP {status}")

    async def _request(self, method: str, path: str, payload: dict | None = None) -> Any:
        """Authenticated call; refreshes the access token when needed."""
        if self._access_expiring():
            await self.refresh_tokens()
        status, body = await self._send(method, path, payload, auth=True)
        if status == 401:
            await self.refresh_tokens()
            status, body = await self._send(method, path, payload, auth=True)
            if status == 401:
                raise DomoAuthError(_detail(body))
        if status != 200:
            self._raise_for(status, body)
        return body

    def _access_expiring(self) -> bool:
        exp = jwt_claims(self.access).get("exp")
        return exp is None or exp - time.time() < ACCESS_REFRESH_MARGIN

    def _set_tokens(self, body: Any) -> None:
        if not isinstance(body, dict) or not body.get("access") or not body.get("refresh"):
            raise DomoConnectionError("no tokens in response")
        self.access = body["access"]
        self.refresh = body["refresh"]
        if self._on_tokens:
            self._on_tokens(self.access, self.refresh)

    # -- auth ----------------------------------------------------------------

    async def request_otp(self, phone: str) -> str:
        """Send the login SMS. Returns the verification session."""
        status, body = await self._send(
            "POST",
            "verification/RequestOTP",
            {"purpose": "login", "address": phone, "client_secret": self.client_secret},
            auth=False,
        )
        if status != 200:
            self._raise_for(status, body)
        return body["session"]

    async def login(self, session: str, otp: str) -> str:
        """Confirm the SMS code and log in. Returns the DOMO user id."""
        status, body = await self._send(
            "POST",
            "verification/SubmitOTP",
            {"session": session, "otp": otp, "client_secret": self.client_secret},
            auth=False,
        )
        if status != 200:
            self._raise_for(status, body)
        session = body.get("session") or session
        status, body = await self._send(
            "POST",
            "accounts/Login",
            {
                "session_data": {
                    "device_id": self.device_id,
                    "platform": PLATFORM,
                    "device_os": DEVICE_OS,
                    "device_model": DEVICE_MODEL,
                    "lang": self._lang,
                    "app_version": APP_VERSION,
                },
                "verification_data": {"session": session, "client_secret": self.client_secret},
            },
            auth=False,
        )
        if status != 200:
            self._raise_for(status, body)
        self._set_tokens(body)
        return body["user_id"]

    async def refresh_tokens(self) -> None:
        old_refresh = self.refresh
        async with self._refresh_lock:
            if self.refresh != old_refresh and not self._access_expiring():
                return  # another caller refreshed while we waited
            if not self.refresh:
                raise DomoAuthError("no refresh token")
            status, body = await self._send(
                "POST", "accounts/RefreshToken", {"refresh": self.refresh}, auth=False
            )
            if status in (400, 401, 403):
                raise DomoAuthError(_detail(body))
            if status != 200:
                self._raise_for(status, body)
            self._set_tokens(body)

    # -- data ----------------------------------------------------------------

    async def homes(self) -> list[dict[str, Any]]:
        return await self._request("GET", "home/HomeList")

    async def refresh_account(self, service: str, account_id: str) -> dict[str, Any]:
        """Ask DOMO to re-sync one account with its provider (the app's pull-to-refresh)."""
        return await self._request("POST", f"{service}/AccountRefresh", {"id": account_id})

    async def daily_usage(
        self, service: str, account_id: str, year: int, month: int
    ) -> list[dict[str, Any]]:
        body = await self._request(
            "GET", f"{service}/DailyUsageStats?account={account_id}&year={year}&month={month}"
        )
        return body.get("usage_data") or []


def iter_accounts(homes: list[dict[str, Any]]):
    """Yield `(home, service_key, account)` for every utility account in every home.

    A service holds one `account` plus an `accounts` list for extra ones.
    """
    for home in homes:
        for key, service in home.items():
            if not isinstance(service, dict) or "accounts" not in service:
                continue
            seen: set[str] = set()
            for account in [service.get("account"), *(service.get("accounts") or [])]:
                if isinstance(account, dict) and account.get("id") and account["id"] not in seen:
                    seen.add(account["id"])
                    yield home, key, account


FLAT_LABEL = {"ru": "кв.", "uz": "xonadon", "en": "apt."}


def home_label(home: dict[str, Any], language: str = "ru") -> str:
    if home.get("name"):
        return home["name"]
    parts = [home.get("street_name"), home.get("house_number")]
    label = " ".join(p for p in parts if p)
    if home.get("flat_number"):
        label += f", {FLAT_LABEL.get(language, FLAT_LABEL['ru'])} {home['flat_number']}"
    return label or "DOMO"


def latest_day(usage: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Most recent day that has a usage value."""
    days = [d for d in usage if d.get("usage") is not None and d.get("date")]
    return max(days, key=lambda d: d["date"]) if days else None
