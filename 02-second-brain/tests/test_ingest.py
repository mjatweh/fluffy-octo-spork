import shutil

from second_brain import frontmatter
from second_brain.ingest import ingest


def _quiet(_):
    pass


def test_dry_run_ingest_files_notes(vault, inbox):
    results = ingest(inbox, vault, dry_run=True, log=_quiet)
    assert {r["status"] for r in results} == {"ingested"}
    assert len(results) == 6
    by_file = {r["file"]: r for r in results}
    assert by_file["apartment_lease.txt"]["note"] == "Life Admin/Housing/Residential Lease Agreement.md"
    assert by_file["auto_insurance_policy.txt"]["note"].startswith("Life Admin/Insurance/")
    assert by_file["acme_services_agreement.md"]["note"].startswith("Business/Contracts/")
    for name in ["apartment_lease.txt", "receipt_photo_coffee_machine.png", "acme_services_agreement.md"]:
        assert (vault / "Attachments" / name).is_file()
    assert (inbox / "apartment_lease.txt").exists()  # external inbox: originals kept by default

    meta, body = frontmatter.parse((vault / by_file["apartment_lease.txt"]["note"]).read_text())
    assert meta["type"] == "lease-agreement"
    assert meta["renewal_date"] == "2027-03-01"
    assert meta["parties"] == ["Oakwood Property Management LLC", "Jamie Rivera"]
    assert meta["source_file"] == "[[apartment_lease.txt]]"
    assert meta["extracted_by"] == "heuristic" and len(meta["source_sha256"]) == 64
    assert "![[apartment_lease.txt]]" in body and "[[Housing]]" in body and "[[Jamie Rivera]]" in body

    img = (vault / by_file["receipt_photo_coffee_machine.png"]["note"]).read_text()
    assert "![[receipt_photo_coffee_machine.png]]" in img and "linked only" in img


def test_ingest_is_idempotent(vault, inbox):
    ingest(inbox, vault, dry_run=True, log=_quiet)
    notes_before = sorted(vault.rglob("*.md"))
    again = ingest(inbox, vault, dry_run=True, log=_quiet)
    assert {r["status"] for r in again} == {"skipped"}
    assert sorted(vault.rglob("*.md")) == notes_before
    # renamed copy of the same bytes is still recognised
    shutil.copy(inbox / "apartment_lease.txt", inbox / "lease_copy.txt")
    by_file = {r["file"]: r for r in ingest(inbox, vault, dry_run=True, log=_quiet)}
    assert by_file["lease_copy.txt"]["status"] == "skipped"


def test_related_links_by_shared_party(ingested):
    invoice = (ingested / "Finance/Invoice 2026-0917.md").read_text()
    assert "- [[Consulting Services Agreement]]" in invoice  # shares Acme Corp / Rivera Studio LLC


def test_in_vault_inbox_moves_originals(vault, inbox):
    drop = vault / "00 Inbox"
    for f in inbox.iterdir():
        shutil.copy(f, drop / f.name)
    ingest(drop, vault, dry_run=True, log=_quiet)
    assert [p.name for p in drop.iterdir()] == [".gitkeep"]  # inbox zero
    assert (vault / "Attachments" / "apartment_lease.txt").exists()


def test_same_name_different_content_gets_unique_attachment(vault, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "policy.txt").write_text("Home insurance policy, premium $100, expires 2027-01-01")
    (b / "policy.txt").write_text("Renters insurance policy, premium $50, expires 2027-02-01")
    ingest(a, vault, dry_run=True, log=_quiet)
    r = ingest(b, vault, dry_run=True, log=_quiet)[0]
    assert r["status"] == "ingested"
    assert len(list((vault / "Attachments").glob("policy*.txt"))) == 2


def test_claude_extraction_with_mock_client(vault, inbox, fake_client):
    for f in list(inbox.iterdir()):
        if f.name != "apartment_lease.txt":
            f.unlink()
    client = fake_client({
        "title": "Apartment Lease - 12 Oak St", "category": "lease", "doc_type": "lease-agreement",
        "summary": "12-month lease for Apt 4B at $2,400/month.", "parties": ["Oakwood Property Management LLC", "Jamie Rivera"],
        "dates": [{"label": "renewal", "date": "2027-03-01"}, {"label": "Notice deadline", "date": "2026-12-30"},
                  {"label": "bogus", "date": "not-a-date"}],
        "amounts": ["$2,400/month rent"], "tags": ["Lease", "housing"]})
    r = ingest(inbox, vault, client=client, log=_quiet)[0]
    assert r["extracted_by"] == "claude"
    assert r["note"] == "Life Admin/Housing/Apartment Lease - 12 Oak St.md"
    meta, body = frontmatter.parse((vault / r["note"]).read_text())
    assert meta["renewal_date"] == "2027-03-01" and meta["notice_deadline_date"] == "2026-12-30"
    assert "bogus_date" not in meta and meta["tags"] == ["lease", "housing"]
    assert "12-month lease" in body
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "apartment_lease.txt" in call["messages"][0]["content"]


def test_refusal_falls_back_to_heuristics(vault, inbox, fake_client):
    client = fake_client("{}", stop_reason="refusal")
    results = ingest(inbox, vault, client=client, log=_quiet)
    assert all(r["extracted_by"] == "heuristic" for r in results)


def test_model_override(vault, inbox, fake_client, monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("SECOND_BRAIN_FALLBACKS", "0")
    client = fake_client("not json")
    ingest(inbox, vault, client=client, log=_quiet)
    assert client.calls[0]["model"] == "claude-sonnet-5-5" and "betas" not in client.calls[0]
