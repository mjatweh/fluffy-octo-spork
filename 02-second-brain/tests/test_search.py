import time

from second_brain.index import refresh, search, stem, tokenize
from second_brain.qa import ask


def test_stemming():
    assert stem("renewal") == stem("renews") == stem("renewed") == stem("renew")
    assert stem("policies") == stem("policy")
    assert stem("expires") == stem("expiry") == stem("expiration")
    assert tokenize("The lease is renewing!") == ["leas", "renew"]


def test_search_ranks_relevant_note_first(ingested):
    assert search(ingested, "lease renewal notice")[0]["path"] == "Life Admin/Housing/Residential Lease Agreement.md"
    assert search(ingested, "car insurance deductible")[0]["name"] == "Auto Insurance Policy Declarations"
    assert search(ingested, "Acme retainer invoice")[0]["name"] == "Invoice 2026-0917"
    top = search(ingested, "newsletter")[0]
    assert top["name"] == "Q4 planning meeting notes" and "newsletter" in top["snippet"]
    assert search(ingested, "zzzz nonexistent") == []


def test_index_is_incremental(ingested):
    data = refresh(ingested)
    n = len(data["docs"])
    note = ingested / "Notes" / "Boat.md"
    note.write_text("# Boat\nMarina slip rental for the sailboat.\n")
    assert search(ingested, "sailboat marina")[0]["path"] == "Notes/Boat.md"
    assert len(refresh(ingested)["docs"]) == n + 1
    note.unlink()
    assert search(ingested, "sailboat") == []
    assert (ingested / ".second_brain" / "index.json").exists()


def test_templates_and_attachments_not_indexed(ingested):
    docs = refresh(ingested, force=True)["docs"]
    assert not any(p.startswith(("Templates/", "Attachments/")) for p in docs)


def test_ask_offline_returns_snippets_and_date(ingested):
    out = ask(ingested, "when does my lease renew?", dry_run=True)
    assert "Likely answer: renewal = 2027-03-01" in out
    assert "[[Residential Lease Agreement]]" in out


def test_ask_with_mock_claude(ingested, fake_client):
    client = fake_client("Your lease renews on 2027-03-01 [[Residential Lease Agreement]].")
    out = ask(ingested, "when does my lease renew?", client=client)
    assert out.startswith("Your lease renews")
    sent = client.calls[0]["messages"][0]["content"]
    assert '<note name="Residential Lease Agreement">' in sent and "Question: when does my lease renew?" in sent
    assert "wikilink" in client.calls[0]["system"]
