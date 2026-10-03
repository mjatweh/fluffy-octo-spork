from second_brain import frontmatter


def test_roundtrip():
    meta = {"title": "Lease: 12 Oak St", "type": "lease", "tags": ["lease", "renewal"], "renewal_date": "2027-03-01",
            "notice_days": 60, "amounts": ["$2,400 per month"], "source_file": "[[lease.txt]]", "empty": []}
    text = frontmatter.render(meta, "# Body\n")
    assert "renewal_date: 2027-03-01\n" in text  # unquoted -> Obsidian date property
    assert "empty" not in text
    parsed, body = frontmatter.parse(text)
    assert body == "# Body\n"
    assert parsed == {k: v for k, v in meta.items() if v != []}


def test_mini_parser_without_yaml():
    raw = "title: X\ntags: [a, b]\nlist:\n  - one\n  - \"two: 2\"\nn: 3\nflag: true\nd: 2026-01-02"
    assert frontmatter._mini_parse(raw) == {"title": "X", "tags": ["a", "b"], "list": ["one", "two: 2"],
                                            "n": 3, "flag": True, "d": "2026-01-02"}


def test_no_frontmatter():
    assert frontmatter.parse("# hi") == ({}, "# hi")
