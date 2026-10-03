from pathlib import Path

import pytest

from second_brain.classify import classify, find_amounts, find_parties, heuristic_metadata, label_dates, notice_days
from second_brain.extract import extract_text

SAMPLES = Path(__file__).resolve().parent.parent / "sample_inbox"


def meta_for(name):
    text, _ = extract_text(SAMPLES / name)
    return heuristic_metadata(text, name)


@pytest.mark.parametrize("name,category,folder,dtype", [
    ("apartment_lease.txt", "lease", "Life Admin/Housing", "lease-agreement"),
    ("auto_insurance_policy.txt", "insurance", "Life Admin/Insurance", "auto-insurance"),
    ("acme_services_agreement.md", "contract", "Business/Contracts", "service-agreement"),
    ("invoice_2026_0917.txt", "finance", "Finance", "invoice"),
    ("meeting-notes-q4-planning.md", "note", "Notes", "note"),
])
def test_sample_classification(name, category, folder, dtype):
    m = meta_for(name)
    assert (m["category"], m["folder"], m["doc_type"]) == (category, folder, dtype)


def test_lease_metadata():
    m = meta_for("apartment_lease.txt")
    assert m["title"] == "Residential Lease Agreement"
    assert m["parties"] == ["Oakwood Property Management LLC", "Jamie Rivera"]
    assert m["dates"]["expiry_date"] == "2027-02-28"
    assert m["dates"]["renewal_date"] == "2027-03-01"
    assert m["dates"]["start_date"] == "2026-03-01"
    assert m["notice_days"] == 60
    assert m["dates"]["notice_deadline_date"] == "2026-12-30"  # 60 days before end of term
    assert "$2,400 per month" in m["amounts"]
    assert "renewal" in m["tags"]


def test_contract_parties_from_between_clause():
    m = meta_for("acme_services_agreement.md")
    assert m["parties"] == ["Rivera Studio LLC", "Acme Corp"]
    assert m["dates"]["expiry_date"] == "2027-03-31"
    assert m["dates"]["notice_deadline_date"] == "2027-03-01"


def test_date_formats_and_labels():
    text = ("Policy effective 03/01/2026.\nCoverage expires on 1st March 2027.\n"
            "Renews automatically on Mar. 2, 2027.\nPayment due: 2026-11-05")
    assert label_dates(text) == {"start_date": "2026-03-01", "expiry_date": "2027-03-01",
                                 "renewal_date": "2027-03-02", "due_date": "2026-11-05"}


def test_unlabeled_date_becomes_document_date():
    assert label_dates("Call notes, 2026-09-01") == {"document_date": "2026-09-01"}


def test_invalid_dates_ignored():
    assert label_dates("expires 2026-02-30") == {}


def test_amounts_and_notice():
    assert find_amounts("Fee $1,250.50 per month, deposit USD 900; $1,250.50 again") == ["$1,250.50 per month", "USD 900", "$1,250.50"]
    assert notice_days("with thirty (30) days prior written notice") == 30
    assert notice_days("no notice clause") is None


def test_role_lines():
    assert find_parties("Landlord: Acme Homes, a Delaware corporation\nTenant: Pat Doe") == ["Acme Homes", "Pat Doe"]


def test_unclassifiable_goes_to_unsorted():
    assert classify("lorem ipsum dolor sit amet", "random.txt") == ("other", "Notes/Unsorted")


def test_filename_boosts_category():
    assert classify("", "home_insurance_policy.pdf")[0] == "insurance"
