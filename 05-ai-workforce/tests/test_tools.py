import pytest

from workforce.agent import execute_tool
from workforce.tools import build_registry, csv_stats, html_to_text, run_sibling_cli


def test_csv_stats(tmp_path):
    p = tmp_path / "rev.csv"
    p.write_text("month,channel,revenue\nJan,ads,\"1,000\"\nJan,seo,500\nFeb,ads,1500\n")
    s = csv_stats(p, group_by="channel")
    assert s["rows"] == 3
    assert s["columns"]["revenue"] == {"type": "numeric", "count": 3, "sum": 3000.0, "mean": 1000.0,
                                       "median": 1000.0, "min": 500.0, "max": 1500.0}
    assert s["columns"]["channel"]["top"][0] == ("ads", 2)
    assert s["group_by"]["channel"]["ads"] == {"_count": 2, "revenue": 2500.0}


def test_analyze_csv_tool_stays_in_workspace(make_ctx):
    reg = build_registry()
    text, err = execute_tool(reg.get("analyze_csv"), {"path": "../../etc/passwd"}, make_ctx())
    assert err


def test_html_to_text():
    assert html_to_text("<html><style>x{}</style><h1>Hi &amp; bye</h1><p>para</p><script>evil()</script></html>") == "Hi & bye\npara"


def test_web_fetch_rejects_non_http(make_ctx):
    text, err = execute_tool(build_registry().get("web_fetch"), {"url": "file:///etc/passwd"}, make_ctx())
    assert err and "http" in text


def test_run_sibling_allowlist(tmp_path):
    siblings = {"exec-assistant": {"dir": "sib", "module": "json.tool", "commands": ["--help"]},
                "x": {"dir": "sib", "module": "m", "commands": ["morning"]}}
    with pytest.raises(PermissionError):
        run_sibling_cli(siblings, tmp_path, "unknown", ["morning"])
    with pytest.raises(PermissionError):
        run_sibling_cli(siblings, tmp_path, "x", ["rm"])
    with pytest.raises(PermissionError):
        run_sibling_cli(siblings, tmp_path, "x", ["morning", "a;b"])
    assert "not installed" in run_sibling_cli(siblings, tmp_path, "x", ["morning"])
    (tmp_path / "sib").mkdir()
    assert run_sibling_cli(siblings, tmp_path, "exec-assistant", ["--help"]).startswith("exit=0")


def test_send_message_without_webhook(make_ctx):
    text, err = execute_tool(build_registry().get("send_message"), {"text": "hi"}, make_ctx())
    assert not err and "not set" in text
