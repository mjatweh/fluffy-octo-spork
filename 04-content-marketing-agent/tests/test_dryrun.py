import pytest

from content_agent import generators, prompts, render
from content_agent.cli import main
from content_agent.validators import validate

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("key", list(prompts.TYPES))
def test_dry_run_every_type_is_valid(brand, key):
    res = generators.generate(key, "Why your ChatGPT pilot failed", brand, dry_run=True)
    assert isinstance(res.content, prompts.TYPES[key].cls)
    assert res.issues == [] and validate(res.content, brand.banned_words) == []
    assert render.to_markdown(res.content).strip()


def test_dry_run_is_deterministic(brand):
    a = generators.generate("linkedin", "Topic A", brand, dry_run=True).content
    b = generators.generate("linkedin", "Topic A", brand, dry_run=True).content
    assert a == b


def test_newsletter_html(brand):
    nl = generators.generate("newsletter", "Client data safety", brand, dry_run=True).content
    html = render.newsletter_html(nl)
    assert html.startswith("<!doctype html>") and nl.cta_url in html and "<ul>" in html


def test_md_to_html():
    out = render.md_to_html("Hi **there** [link](https://x.y)\n\n- a\n- b\n\n1. one")
    assert "<strong>there</strong>" in out and '<a href="https://x.y">link</a>' in out
    assert "<ul><li>a</li><li>b</li></ul>" in out and "<ol><li>one</li></ol>" in out
    assert "&lt;script&gt;" in render.md_to_html("<script>")


def test_repurpose_dry_run(brand):
    source = (ROOT / "samples" / "long-article.md").read_text()
    results = generators.repurpose(source, brand, dry_run=True)
    assert [r.key for r in results] == list(generators.REPURPOSE_DEFAULT)
    assert all(r.issues == [] for r in results)
    assert results[0].topic.startswith("How we cut client onboarding")
    assert "14 hours" in render.to_markdown(results[0].content)


def test_review_dry_run_flags_banned_words(brand):
    rev = generators.review("We leverage synergy to revolutionize your firm.", brand, dry_run=True)
    assert rev.voice_score < 50 and any("leverage" in i for i in rev.issues)
    assert "leverage" not in rev.revised_draft.lower() and "use" in rev.revised_draft
    good = generators.review("Your team is drowning in admin. Get hours back on billable hours work.", brand, dry_run=True)
    assert good.overall_score > rev.overall_score


def test_cli_end_to_end(tmp_path, capsys):
    out, vault = tmp_path / "out", tmp_path / "vault"
    assert main(["generate", "newsletter", "--topic", "AI and client data", "--out", str(out), "--vault", str(vault)]) == 0
    md = next((out / "newsletter").glob("*.md"))
    assert md.with_suffix(".html").exists()
    note = next((vault / "Content" / "Drafts" / "newsletter").glob("*-ai-and-client-data.md"))
    text = note.read_text()
    assert text.startswith("---\ntype: \"newsletter\"\nchannel: \"newsletter\"\nstatus: \"draft\"\ntopic: \"AI and client data\"")
    assert main(["calendar", "--period", "month", "--start", "2026-10-05", "--out", str(out)]) == 0
    assert len(next((out / "calendar").glob("*.csv")).read_text().splitlines()) == 57
    draft = tmp_path / "draft.txt"
    draft.write_text("We leverage cutting-edge AI.")
    assert main(["review", str(draft), "--no-save"]) == 0
    assert "leverage" in capsys.readouterr().out
    assert main(["brand", "validate"]) == 0
    assert main(["generate", "fax", "--topic", "x"]) == 1


def test_cli_rejects_incomplete_brand(tmp_path):
    with pytest.raises(SystemExit):
        main(["generate", "x", "--topic", "t", "--brand", str(ROOT / "brand" / "templates")])
