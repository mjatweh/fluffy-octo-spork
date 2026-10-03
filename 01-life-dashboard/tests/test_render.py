import re

from life_dashboard.briefing import template_briefing
from life_dashboard.config import load_config
from life_dashboard.models import Briefing, Email
from life_dashboard.pipeline import build, collect
from life_dashboard.render import VAULT_END, VAULT_START, render_html, render_markdown, write_vault_note


def test_html_has_all_panels_and_is_self_contained(config, day):
    data = collect(config, day)
    html = render_html(data, template_briefing(data), note="test")
    for panel in ("briefing", "schedule", "inbox", "tasks", "tools"):
        assert f'id="{panel}"' in html
    assert "prefers-color-scheme: dark" in html and "Q1 roadmap review" in html
    assert not re.search(r'<(?:link|script)[^>]+(?:href|src)="https?://', html)  # no external assets
    assert "conflict" in html


def test_html_escapes_untrusted_content(config, day):
    data = collect(config, day)
    data.emails.insert(0, Email("Eve <eve@x.com>", "<script>alert(1)</script>", data.generated_at))
    html = render_html(data, template_briefing(data))
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_markdown_briefing(config, day):
    data = collect(config, day)
    md = render_markdown(data, Briefing("Head", "Sum", top_priorities=["X"], risks=[]))
    assert md.startswith("# Daily briefing — Monday, October 5, 2026")
    assert "- X" in md and "## Risks & conflicts\n- Nothing notable." in md
    assert "- [ ] Finish Q1 roadmap deck" in md


def test_vault_note_created_then_updated_in_place(tmp_path, config, day):
    data = collect(config, day)
    path = write_vault_note(tmp_path, data, "# first")
    assert path == tmp_path / "Daily" / "2026-10-05.md"
    assert path.read_text().startswith("---\ndate: 2026-10-05")
    path.write_text(path.read_text() + "\nMy own journal line\n")
    write_vault_note(tmp_path, data, "# second")
    text = path.read_text()
    assert "# second" in text and "# first" not in text and "My own journal line" in text
    assert text.count(VAULT_START) == 1 and text.count(VAULT_END) == 1


def test_vault_note_appends_to_existing_note_without_markers(tmp_path, config, day):
    note = tmp_path / "Daily" / "2026-10-05.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Monday\nwritten by second brain\n")
    write_vault_note(tmp_path, collect(config, day), "# briefing")
    text = note.read_text()
    assert text.startswith("# Monday") and text.rstrip().endswith(VAULT_END)


def test_build_end_to_end_offline(tmp_path, config, day):
    config.vault_path = tmp_path / "vault"
    result = build(config, day=day, offline=True)
    assert result.html.exists() and result.markdown.exists()
    assert (config.output_dir / "briefing.md").exists()
    assert result.vault_note.exists()
    assert all(s.ok for s in result.data.statuses)


def test_broken_connector_reported_not_fatal(config, day):
    config.connectors = [{"type": "ics", "name": "Broken cal", "source": "missing.ics"}, {"type": "sample_tasks"}]
    data = collect(config, day)
    broken, ok = data.statuses
    assert not broken.ok and "not found" in broken.message and ok.ok
    assert "Broken cal" in render_html(data, template_briefing(data))


def test_config_file_loading(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        'timezone = "Europe/Paris"\nvault_path = "~/vault"\noutput_dir = "site"\n'
        '[[connectors]]\ntype = "ics"\nsource = "a.ics"\n'
        '[[connectors]]\ntype = "imap"\nenabled = false\n'
        '[[links]]\nname = "GitHub"\nurl = "https://github.com"\n'
    )
    cfg = load_config(str(cfg_file))
    assert cfg.timezone == "Europe/Paris" and cfg.model == "claude-sonnet-5-5"
    assert cfg.output_dir == tmp_path / "site" and cfg.vault_path.name == "vault"
    assert [c["type"] for c in cfg.connectors] == ["ics"] and cfg.links[0]["name"] == "GitHub"
