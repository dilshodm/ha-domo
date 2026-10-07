"""Tests for the HA-free DOMO client."""
from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import sys
import time

import pytest

# Load api.py directly so the tests don't need Home Assistant installed.
_spec = importlib.util.spec_from_file_location(
    "domo_api", Path(__file__).parents[1] / "custom_components/domo/api.py"
)
api = importlib.util.module_from_spec(_spec)
sys.modules["domo_api"] = api
_spec.loader.exec_module(api)


def jwt(exp: float) -> str:
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'HS256'})}.{b64({'sub': 'u1', 'exp': int(exp)})}.sig"


class FakeResponse:
    def __init__(self, status: int, body):
        self.status = status
        self._body = body

    async def json(self, content_type=None):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Answers from a queue of `(path, status, body)` and records requests."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def request(self, method, url, json=None, headers=None, timeout=None):
        path = url.removeprefix(api.BASE_URL)
        self.calls.append((method, path, json, headers))
        expected, status, body = self.replies.pop(0)
        assert path == expected, f"expected {expected}, got {path}"
        return FakeResponse(status, body)


def client(session, access=None, refresh="r0", tokens=None):
    return api.DomoClient(
        session,
        "dev-1",
        "secret-1",
        access=access,
        refresh=refresh,
        on_tokens=(lambda a, r: tokens.append((a, r))) if tokens is not None else None,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+998 97 769 54 50", "+998977695450"),
        ("998977695450", "+998977695450"),
        ("977695450", "+998977695450"),
    ],
)
def test_normalize_phone(raw, expected):
    assert api.normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["12345", "+7 912 345 67 89", ""])
def test_normalize_phone_rejects(raw):
    with pytest.raises(ValueError):
        api.normalize_phone(raw)


async def test_login_flow_sends_device_identity_and_stores_tokens():
    access, refresh = jwt(time.time() + 7 * 86400), jwt(time.time() + 365 * 86400)
    session = FakeSession(
        [
            ("verification/RequestOTP", 200, {"session": "s1", "retry_after": 60}),
            ("verification/SubmitOTP", 200, {"session": "s1"}),
            ("accounts/Login", 200, {"user_id": "u1", "access": access, "refresh": refresh}),
        ]
    )
    tokens = []
    c = client(session, refresh=None, tokens=tokens)

    assert await c.request_otp("+998977695450") == "s1"
    assert await c.login("s1", "123456") == "u1"

    otp_body = session.calls[0][2]
    assert otp_body == {"purpose": "login", "address": "+998977695450", "client_secret": "secret-1"}
    login_body = session.calls[2][2]
    assert login_body["verification_data"] == {"session": "s1", "client_secret": "secret-1"}
    assert login_body["session_data"]["device_id"] == "dev-1"
    assert session.calls[2][3]["Device-Id"] == "dev-1"
    assert "Authorization" not in session.calls[2][3]
    assert tokens == [(access, refresh)]


async def test_request_otp_error_carries_code_and_retry_after():
    session = FakeSession(
        [("verification/RequestOTP", 429, {"detail": "too_many_requests", "retry_after": 42})]
    )
    with pytest.raises(api.DomoRequestError) as err:
        await client(session).request_otp("+998977695450")
    assert err.value.code == "too_many_requests"
    assert err.value.retry_after == 42


async def test_expiring_access_is_refreshed_before_the_call():
    new_access, new_refresh = jwt(time.time() + 7 * 86400), jwt(time.time() + 365 * 86400)
    session = FakeSession(
        [
            ("accounts/RefreshToken", 200, {"access": new_access, "refresh": new_refresh}),
            ("home/HomeList", 200, []),
        ]
    )
    tokens = []
    c = client(session, access=jwt(time.time() + 3600), tokens=tokens)

    assert await c.homes() == []
    assert session.calls[0][2] == {"refresh": "r0"}
    assert session.calls[1][3]["Authorization"] == f"Bearer {new_access}"
    assert tokens == [(new_access, new_refresh)]


async def test_401_triggers_one_refresh_and_retry():
    fresh = jwt(time.time() + 7 * 86400)
    session = FakeSession(
        [
            ("home/HomeList", 401, {"detail": "Invalid authentication credentials"}),
            ("accounts/RefreshToken", 200, {"access": fresh, "refresh": "r1"}),
            ("home/HomeList", 200, [{"id": "h1"}]),
        ]
    )
    c = client(session, access=jwt(time.time() + 5 * 86400))
    assert await c.homes() == [{"id": "h1"}]
    assert c.refresh == "r1"


async def test_rejected_refresh_raises_auth_error():
    session = FakeSession(
        [
            (
                "accounts/RefreshToken",
                401,
                {"detail": {"error": "invalid_token", "message": "The token is invalid"}},
            )
        ]
    )
    with pytest.raises(api.DomoAuthError, match="invalid_token"):
        await client(session, access=None).homes()


async def test_server_error_is_connection_error():
    session = FakeSession([("home/HomeList", 502, None)])
    with pytest.raises(api.DomoConnectionError):
        await client(session, access=jwt(time.time() + 5 * 86400)).homes()


HOMES = [
    {
        "id": "h1",
        "name": None,
        "street_name": "Navoiy",
        "house_number": "7",
        "flat_number": "98",
        "natural_gas": {
            "account": {"id": "g1", "account_number": "1012017937", "balance": "300015.50"},
            "accounts": [{"id": "g2", "balance": "1.00"}, {"id": "g1"}],
            "analytics": {"this_month": None},
        },
        "liquefied_gas": {"account": None, "accounts": []},
        "telephony": {"accounts": [], "analytics": None},
        "analytics_available": False,
        "region": {"id": "r1", "name": "Tashkent"},
    }
]


def test_iter_accounts_merges_account_and_accounts_without_duplicates():
    found = [(h["id"], s, a["id"]) for h, s, a in api.iter_accounts(HOMES)]
    assert found == [("h1", "natural_gas", "g1"), ("h1", "natural_gas", "g2")]


def test_home_label_falls_back_to_address():
    assert api.home_label(HOMES[0]) == "Navoiy 7, кв. 98"
    assert api.home_label({"name": "Дача"}) == "Дача"


def test_latest_day_skips_null_usage():
    usage = [
        {"date": "2026-10-05", "usage": None},
        {"date": "2026-10-04", "usage": 64.0},
        {"date": "2026-10-03", "usage": 18.0},
    ]
    assert api.latest_day(usage)["date"] == "2026-10-04"
    assert api.latest_day([]) is None


def test_iter_accounts_sees_an_account_added_later():
    before = {a["id"] for _, _, a in api.iter_accounts(HOMES)}
    later = [
        {
            **HOMES[0],
            "hot_water": {"account": {"id": "w1", "balance": "0.00"}, "accounts": []},
        }
    ]
    after = {a["id"] for _, _, a in api.iter_accounts(later)}
    assert after - before == {"w1"}


async def test_refresh_account_posts_the_account_id():
    session = FakeSession([("natural_gas/AccountRefresh", 200, {"id": "g1", "balance": "1.00"})])
    c = client(session, access=jwt(time.time() + 5 * 86400))
    assert (await c.refresh_account("natural_gas", "g1"))["balance"] == "1.00"
    assert session.calls[0][:3] == ("POST", "natural_gas/AccountRefresh", {"id": "g1"})


def test_home_label_flat_word_follows_language():
    assert api.home_label(HOMES[0], "uz") == "Navoiy 7, xonadon 98"
    assert api.home_label(HOMES[0], "en") == "Navoiy 7, apt. 98"
