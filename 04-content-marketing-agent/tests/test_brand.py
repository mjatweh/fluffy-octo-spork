from content_agent.brand import (BRAND_FILES, PROJECT_ROOT, bullets, copy_templates, interview, load_brand,
                                 parse_sections, resolve_brand_dir, show_brand, validate_brand)

import pytest


def test_example_brand_loads_and_validates(brand):
    errors, warnings = validate_brand(brand)
    assert errors == [] and warnings == []
    assert brand.name == "Northbeam AI"
    assert "professional services" in brand.mission
    assert len(brand.pains) >= 3 and brand.desires and brand.objections and brand.language
    assert {"AI Ops Audit", "Automation Build Sprint"} <= set(brand.offers)
    assert len(brand.pillars) == 4 and all(p.topics for p in brand.pillars)
    assert len(brand.example_posts) == 3


def test_banned_words_parsed_without_reasons(brand):
    assert "leverage" in brand.banned_words and "game-changer" in brand.banned_words
    assert brand.banned_map["leverage"] == 'say "use"'
    assert all("—" not in w for w in brand.banned_words)


def test_blank_templates_fail_validation():
    errors, _ = validate_brand(load_brand(PROJECT_ROOT / "brand" / "templates"))
    assert any("Mission" in e for e in errors)
    assert any("offers.md" in e for e in errors) and any("content_pillars.md" in e for e in errors)


def test_parse_sections_strips_comments():
    s = parse_sections("# T\n\n## A\nhello <!-- hidden -->\n- x\n## B\n<!-- only guidance -->\n")
    assert s == {"A": "hello \n- x", "B": ""}
    assert bullets(s["A"]) == ["x"]


def test_missing_files_reported(tmp_path):
    (tmp_path / "brand.md").write_text("## Mission\nx\n")
    errors, _ = validate_brand(load_brand(tmp_path))
    assert any("missing file: icp.md" in e for e in errors)


def test_resolve_brand_dir_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAND_DIR", str(tmp_path))
    assert resolve_brand_dir() == tmp_path
    assert resolve_brand_dir("other") .name == "other"


def test_load_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_brand(tmp_path / "nope")


def test_interview_writes_valid_brand(tmp_path):
    answers = iter([
        "Acme Studio", "We help bakeries sell more online.", "Done-for-you websites.",
        "friendly, direct", "fresh, simple", "synergy, leverage", "Post one|Post two",
        "Bakery owners, 1-10 staff", "no time, low traffic, confusing tech", "more orders, less admin",
        "too expensive, too slow", "Instagram, Facebook groups", "get more orders, I'm not techy",
        "Website Sprint", "Two-week build, $3k, acme.com/sprint", "Recipes, Behind the scenes, Tips",
    ])
    out = []
    interview(tmp_path, ask=lambda q: next(answers), say=out.append)
    assert all((tmp_path / f).exists() for f in BRAND_FILES)
    b = load_brand(tmp_path)
    errors, _ = validate_brand(b)
    assert errors == []
    assert b.banned_words == ["synergy", "leverage"] and b.example_posts == ["Post one", "Post two"]
    assert [p.name for p in b.pillars] == ["Recipes", "Behind the scenes", "Tips"]
    assert "Acme Studio" in show_brand(b)
    with pytest.raises(FileExistsError):
        interview(tmp_path, ask=lambda q: "", say=out.append)


def test_copy_templates(tmp_path):
    copy_templates(tmp_path)
    assert all((tmp_path / f).exists() for f in BRAND_FILES)
