import builtins
import zipfile

from second_brain.extract import extract_text, kind


def test_kinds(tmp_path):
    assert [kind(tmp_path / n) for n in ["a.TXT", "b.md", "c.pdf", "d.docx", "e.jpg", "f.zip", "g.html"]] == \
        ["text", "text", "pdf", "docx", "image", "binary", "html"]


def test_docx(tmp_path):
    p = tmp_path / "nda.docx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", '<w:document><w:body><w:p><w:r><w:t>Mutual NDA</w:t></w:r></w:p>'
                                        '<w:p><w:r><w:t>Expires on 2027-01-01 &amp; renews</w:t></w:r></w:p></w:body></w:document>')
    text, warn = extract_text(p)
    assert warn is None and text.splitlines()[:2] == ["Mutual NDA", "Expires on 2027-01-01 & renews"]


def test_html(tmp_path):
    p = tmp_path / "receipt.html"
    p.write_text("<html><style>x{}</style><body><h1>Receipt</h1><p>Total &pound;12</p></body></html>")
    text, _ = extract_text(p)
    assert "Receipt" in text and "£12" in text and "x{}" not in text


def test_pdf_without_pypdf_is_graceful(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "pypdf":
            raise ImportError
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    p = tmp_path / "scan.pdf"
    p.write_bytes(b"%PDF-1.4 not really")
    text, warn = extract_text(p)
    assert text == "" and "pypdf" in warn


def test_corrupt_file_does_not_raise(tmp_path):
    p = tmp_path / "broken.docx"
    p.write_bytes(b"not a zip")
    text, warn = extract_text(p)
    assert text == "" and "failed" in warn


def make_pdf(lines):
    stream = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(f"({l}) Tj T*" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += f"{i} 0 obj\n{o}\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n"
    return out.encode()


def test_pdf_with_pypdf(tmp_path, vault):
    import pytest

    pytest.importorskip("pypdf")
    from second_brain.ingest import ingest

    (tmp_path / "drop").mkdir()
    (tmp_path / "drop" / "home_policy.pdf").write_bytes(
        make_pdf(["Home Insurance Policy", "Policy expires on 2027-01-15", "Premium: $1,200 per year"]))
    r = ingest(tmp_path / "drop", vault, dry_run=True, log=lambda m: None)[0]
    assert r["category"] == "insurance"
    assert "expiry_date: 2027-01-15" in (vault / r["note"]).read_text()
