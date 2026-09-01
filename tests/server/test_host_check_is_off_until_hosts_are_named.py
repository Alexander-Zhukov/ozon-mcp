"""MCP's Host check is an exact match, so it can only be turned on by naming hosts.

Enabled with an empty list it refuses every request — including one from a
client using the address it was told to use, which reads as a broken server.
"""

import pytest

from ozon_mcp.mcp_server import _transport_security
from ozon_mcp.settings import get_settings


def test_no_hosts_named_means_no_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "allowed_hosts", [])
    security = _transport_security()
    assert security.enable_dns_rebinding_protection is False


def test_naming_hosts_turns_the_check_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "allowed_hosts", ["ozon-mcp.runetree.ru", "192.168.1.41:*"])
    security = _transport_security()
    assert security.enable_dns_rebinding_protection is True
    assert security.allowed_hosts == ["ozon-mcp.runetree.ru", "192.168.1.41:*"]
