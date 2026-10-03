import json
import os
import stat
import urllib.parse

import pytest

from life_dashboard.connectors import ConnectorError, build_connector
from life_dashboard.connectors import outlook
from life_dashboard.connectors.outlook import OAuthError, parse_messages

GRAPH_PAGE = {
    "value": [
        {
            "subject": "Contract redlines",
            "from": {"emailAddress": {"name": "Dana Lee", "address": "dana@client.com"}},
            "receivedDateTime": "2026-10-05T13:30:00Z",
            "bodyPreview": "Can you  review\r\n the attached by Friday?",
            "isRead": False,
            "flag": {"flagStatus": "flagged"},
        },
        {"subject": "", "from": {"emailAddress": {"address": "noreply@x.com"}},
         "receivedDateTime": "2026-10-04T08:00:00Z", "isRead": True},
    ]
}


@pytest.fixture
def conn(config, tmp_path):
    return build_connector({"type": "outlook", "name": "Work Outlook", "client_id": "app-123",
                            "token_cache": str(tmp_path / "tok.json")}, config)


class FakeServer:
    """Stands in for login.microsoftonline.com + graph.microsoft.com."""

    def __init__(self, token_responses):
        self.token_responses = list(token_responses)
        self.calls = []

    def __call__(self, url, data=None, token=None, timeout=20):
        self.calls.append((url, data, token))
        if url.endswith("/devicecode"):
            return {"device_code": "dev-1", "user_code": "ABCD-EFGH", "interval": 1, "expires_in": 60,
                    "verification_uri": "https://microsoft.com/devicelogin", "message": "Go sign in: ABCD-EFGH"}
        if url.endswith("/token"):
            resp = self.token_responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        if "graph.microsoft.com" in url:
            return GRAPH_PAGE
        raise AssertionError(url)


def test_registered():
    from life_dashboard.connectors import REGISTRY

    assert REGISTRY["outlook"].kind == "email"


def test_parse_messages(config):
    emails = parse_messages(GRAPH_PAGE, "Work Outlook", config.tz)
    first, second = emails
    assert first.sender == "Dana Lee <dana@client.com>"
    assert first.snippet == "Can you review the attached by Friday?"
    assert first.unread and first.flagged and first.source == "Work Outlook"
    assert first.received.hour == 9  # 13:30Z -> 09:30 New York
    assert second.subject == "(no subject)" and second.sender == "noreply@x.com" and not second.unread


def test_device_code_login_polls_until_signed_in(conn, monkeypatch):
    server = FakeServer([OAuthError("authorization_pending"), OAuthError("slow_down"),
                         {"access_token": "at", "refresh_token": "rt-1"}])
    monkeypatch.setattr(outlook, "_request", server)
    prompts, sleeps = [], []
    path = conn.login(prompt=prompts.append, sleep=sleeps.append)
    assert prompts == ["Go sign in: ABCD-EFGH"]
    assert sleeps == [1, 1, 6]  # slow_down adds 5 seconds
    assert json.loads(path.read_text())["refresh_token"] == "rt-1"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert server.calls[0][1]["scope"] == "offline_access Mail.Read"


def test_login_declined_raises(conn, monkeypatch):
    monkeypatch.setattr(outlook, "_request", FakeServer([OAuthError("authorization_declined", "user said no")]))
    with pytest.raises(OAuthError, match="authorization_declined"):
        conn.login(prompt=lambda m: None, sleep=lambda s: None)


def test_fetch_refreshes_rotates_token_and_queries_graph(conn, day, monkeypatch):
    conn.token_cache.write_text(json.dumps({"refresh_token": "rt-old"}))
    server = FakeServer([{"access_token": "at-new", "refresh_token": "rt-new"}])
    monkeypatch.setattr(outlook, "_request", server)
    emails = conn.fetch(day)
    assert [e.subject for e in emails] == ["Contract redlines", "(no subject)"]
    assert server.calls[0][1]["refresh_token"] == "rt-old"
    assert json.loads(conn.token_cache.read_text())["refresh_token"] == "rt-new"
    url, _, token = server.calls[1]
    assert token == "at-new" and "/me/mailFolders/inbox/messages" in url
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert query["$filter"] == ["receivedDateTime ge 2026-10-03T04:00:00Z and isRead eq false"]
    assert query["$top"] == ["25"]


def test_fetch_without_sign_in_explains_next_step(conn, day):
    with pytest.raises(ConnectorError, match="life_dashboard auth"):
        conn.fetch(day)


def test_expired_refresh_token_asks_to_sign_in_again(conn, day, monkeypatch):
    conn.token_cache.write_text(json.dumps({"refresh_token": "rt-old"}))
    monkeypatch.setattr(outlook, "_request", FakeServer([OAuthError("invalid_grant", "expired")]))
    with pytest.raises(ConnectorError, match="sign-in expired"):
        conn.fetch(day)


def test_client_id_from_env(config, monkeypatch):
    monkeypatch.setenv("OUTLOOK_CLIENT_ID", "env-app")
    c = build_connector({"type": "outlook", "client_id_env": "OUTLOOK_CLIENT_ID"}, config)
    assert c.client_id == "env-app"
    assert c.token_cache.name == "outlook-outlook.json"


def test_missing_client_id(config, day):
    with pytest.raises(ConnectorError, match="client_id"):
        build_connector({"type": "outlook"}, config).fetch(day)


def test_auth_command_without_outlook_connector(tmp_path, monkeypatch, capsys):
    from life_dashboard.cli import main

    cfg = tmp_path / "c.toml"
    cfg.write_text('[[connectors]]\ntype = "sample_email"\n')
    assert main(["-c", str(cfg), "auth"]) == 1
    assert "type = \"outlook\"" in capsys.readouterr().err
