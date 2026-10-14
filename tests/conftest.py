"""Shared test setup.

Every test runs with:
- no GROQ_API_KEY in the environment,
- outbound network blocked (only loopback connections, which asyncio uses
  internally on Windows, are allowed),
- an empty in-memory redemption list.
"""

import ipaddress
import socket

import pytest

import loyalty_data as data

_real_connect = socket.socket.connect


def _is_loopback(address) -> bool:
    if not isinstance(address, tuple):
        return False
    try:
        return ipaddress.ip_address(address[0]).is_loopback
    except ValueError:
        return False


def _guarded_connect(self, address):
    if _is_loopback(address):
        return _real_connect(self, address)
    raise RuntimeError(f"Network access is blocked in tests (tried {address!r})")


@pytest.fixture(autouse=True)
def offline_and_keyless(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)


@pytest.fixture(autouse=True)
def reset_redemptions():
    data.REDEMPTION_REQUESTS.clear()
    yield
    data.REDEMPTION_REQUESTS.clear()
