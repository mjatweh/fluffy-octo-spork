"""Offline heuristics: category, document type, parties, dates, amounts.

Deterministic and dependency-free; used directly in --dry-run/offline mode and as
the baseline that Claude's structured extraction refines.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

# category -> (vault folder, keywords). Order breaks ties.
CATEGORIES: dict[str, tuple[str, list[str]]] = {
    "lease": ("Life Admin/Housing", ["lease", "landlord", "tenant", "lessor", "lessee", "rent",
                                     "premises", "security deposit", "tenancy", "mortgage"]),
    "insurance": ("Life Admin/Insurance", ["insurance", "insurer", "insured", "policyholder", "premium",
                                           "coverage", "deductible", "policy number", "claim"]),
    "contract": ("Business/Contracts", ["agreement", "contract", "parties", "statement of work",
                                        "non-disclosure", "confidential", "terminate", "indemnif",
                                        "governing law", "contractor", "services"]),
    "client": ("Business/Clients", ["proposal", "client", "quote", "estimate", "kickoff", "retainer", "scope"]),
    "finance": ("Finance", ["invoice", "receipt", "tax", "bank", "statement", "amount due", "payment due",
                            "balance", "subscription", "paid", "irs"]),
    "health": ("Life Admin/Health", ["patient", "medical", "prescription", "doctor", "clinic", "dental", "vaccin"]),
    "vehicle": ("Life Admin/Vehicles", ["vehicle", "vin", "registration", "dmv", "odometer", "make and model"]),
    "note": ("Notes", ["meeting", "idea", "todo", "notes", "journal", "brainstorm"]),
}
OTHER = ("other", "Notes/Unsorted")
CATEGORY_NAMES = list(CATEGORIES) + ["other"]

SUBTYPES = [  # (regex, doc_type) - first match wins, checked in order
    (r"non-disclosure|\bnda\b", "nda"),
    (r"statement of work|\bsow\b", "statement-of-work"),
    (r"\binvoice\b", "invoice"),
    (r"\breceipt\b", "receipt"),
    (r"\b(auto|car|vehicle) insurance|auto policy", "auto-insurance"),
    (r"\b(home|homeowners?|renters?) insurance", "home-insurance"),
    (r"\b(health|medical|dental) insurance", "health-insurance"),
    (r"\blife insurance", "life-insurance"),
    (r"residential lease|lease agreement|rental agreement", "lease-agreement"),
    (r"master services agreement|\bmsa\b", "msa"),
    (r"(services|consulting|service) agreement", "service-agreement"),
    (r"employment (agreement|contract)|offer letter", "employment"),
    (r"\bproposal\b", "proposal"),
    (r"bank statement", "bank-statement"),
]

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(_MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I), "mdy_name"),
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MON + r",?\s+(\d{4})", re.I), "dmy_name"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "mdy"),  # US convention
]
# context keyword -> frontmatter key. Nearest keyword before the date wins.
DATE_LABELS = [
    (r"renew", "renewal_date"),
    (r"expir|end date|ends on|terminat|until|through|thru|lease end|end of term", "expiry_date"),
    (r"effective|commenc|start|begin|from|inception", "start_date"),
    (r"due|pay by|deadline", "due_date"),
    (r"signed|dated|executed|issued|invoice date", "signed_date"),
    (r"review|inspection|appointment", "review_date"),
]
ROLE_RE = re.compile(
    r"^[ \t>*_-]*(landlord|tenant|lessor|lessee|insurer|insured|named insured|policyholder|carrier|client|"
    r"customer|provider|service provider|contractor|consultant|vendor|company|employer|employee|"
    r"bill to|billed to|from|seller|buyer|party a|party b)\**[ \t]*[:\-][ \t]*\**(.+)$",
    re.I | re.M)
BETWEEN_RE = re.compile(
    r"\bbetween\s+(?:\*\*)?([A-Z][\w&.,' -]{1,60}?)(?:\*\*)?\s*(?:\([^)]*\))?\s*,?\s+and\s+(?:\*\*)?"
    r"([A-Z][\w&.' -]{1,60}?)(?:\*\*)?\s*(?:\(|,|\.\s|\.$|\n|;)", re.S)
AMOUNT_RE = re.compile(
    r"(?:[$€£]|\b(?:USD|EUR|GBP|CAD|AUD)\s)\s?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?"
    r"(?:\s?(?:/|per)\s?(?:month|mo|year|yr|annum|hour|hr))?", re.I)
NOTICE_RE = re.compile(r"\(?(\d{1,3})\)?\s*(?:\(\w+\)\s*)?(?:calendar\s+)?days?['’]?\s+(?:prior\s+|advance\s+)?(?:written\s+)?notice", re.I)


def _mk(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def find_dates(text: str) -> list[tuple[int, dt.date]]:
    found: dict[int, dt.date] = {}
    for rx, fmt in DATE_PATTERNS:
        for m in rx.finditer(text):
            g = m.groups()
            if fmt == "ymd":
                d = _mk(int(g[0]), int(g[1]), int(g[2]))
            elif fmt == "mdy_name":
                d = _mk(int(g[2]), MONTHS[g[0][:3].lower()], int(g[1]))
            elif fmt == "dmy_name":
                d = _mk(int(g[2]), MONTHS[g[1][:3].lower()], int(g[0]))
            else:
                d = _mk(int(g[2]), int(g[0]), int(g[1]))
            if d and 1900 < d.year < 2200 and not any(abs(p - m.start()) < 3 for p in found):
                found[m.start()] = d
    return sorted(found.items())


def label_dates(text: str) -> dict[str, str]:
    """Map semantic labels (renewal_date, expiry_date, ...) to ISO dates."""
    out: dict[str, str] = {}
    for pos, d in find_dates(text):
        line_start = text.rfind("\n", 0, pos) + 1
        ctx = text[max(line_start, pos - 90):pos].lower()
        best, best_at = None, -1
        for rx, label in DATE_LABELS:
            for m in re.finditer(rx, ctx):
                if m.start() > best_at:
                    best, best_at = label, m.start()
        if best and best not in out:
            out[best] = d.isoformat()
    if not out:
        dates = find_dates(text)
        if dates:
            out["document_date"] = dates[0][1].isoformat()
    return out


def notice_days(text: str) -> int | None:
    m = NOTICE_RE.search(text)
    return int(m.group(1)) if m else None


def _clean_party(s: str) -> str:
    s = re.split(r"\s*(?:\(|,\s*(?:a|an|the)\s|;|\s{2,}|\|)", s.strip())[0]
    s = s.strip(" .,:;*_\"'`[]")
    return re.sub(r"\s+", " ", s)[:80]


def find_parties(text: str) -> list[str]:
    seen: dict[str, str] = {}
    candidates = [m.group(2) for m in ROLE_RE.finditer(text)]
    for m in BETWEEN_RE.finditer(text):
        candidates += [m.group(1), m.group(2)]
    for c in candidates:
        p = _clean_party(c)
        if len(p) >= 2 and re.search(r"[A-Za-z]", p) and not re.match(r"^\d", p) and p.lower() not in seen:
            seen[p.lower()] = p
    return list(seen.values())[:6]


def find_amounts(text: str) -> list[str]:
    out: list[str] = []
    for m in AMOUNT_RE.finditer(text):
        a = re.sub(r"\s+", " ", m.group(0)).strip()
        if a not in out:
            out.append(a)
    return out[:6]


def classify(text: str, filename: str = "") -> tuple[str, str]:
    """Return (category, folder)."""
    low, fname = text.lower(), Path(filename).stem.lower().replace("_", " ").replace("-", " ")
    scores = {}
    for cat, (_, kws) in CATEGORIES.items():
        s = sum(min(len(re.findall(r"\b" + re.escape(k), low)), 5) for k in kws)
        s += sum(3 for k in kws if re.search(r"\b" + re.escape(k), fname))
        scores[cat] = s
    cat = max(scores, key=lambda c: scores[c])  # first max wins on ties (dict order)
    if scores[cat] < 2:
        return OTHER
    return cat, CATEGORIES[cat][0]


def doc_type(text: str, category: str, filename: str = "", title: str = "") -> str:
    head = f"{Path(filename).stem.replace('_', ' ')}\n{title}".lower()
    for hay in (head, text[:3000].lower()):  # filename/title beat body mentions
        for rx, t in SUBTYPES:
            if re.search(rx, hay):
                return t
    return {"other": "document"}.get(category, category)


TITLE_WORDS = re.compile(r"agreement|contract|policy|declaration|invoice|receipt|lease|statement|notes?\b|"
                         r"proposal|certificate|report|letter|bill\b", re.I)


def title_for(text: str, filename: str) -> str:
    cands = []
    for line in text.splitlines()[:20]:
        line = re.sub(r"^#+\s*", "", line.strip()).strip("*_ ")
        if 3 <= len(line) <= 90 and re.search(r"[A-Za-z]{3}", line) and ":" not in line:
            cands.append(line.title() if line.isupper() else line)
        if len(cands) == 4:
            break
    if cands:
        return next((c for c in cands if TITLE_WORDS.search(c)), cands[0])
    return re.sub(r"[_-]+", " ", Path(filename).stem).strip().title() or "Untitled"


def summarize(text: str, title: str = "", limit: int = 300) -> str:
    """First meaningful prose sentences (skips headings, the title and short 'Key: value' lines)."""
    keep = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(#+|[-*>]|\d+\.)\s*", "", line).strip()
        line = re.sub(r"^[A-Z][A-Z ]{2,}\.\s*", "", line)  # "1. TERM." style section labels
        line = re.sub(r"\s{2,}", " ", line.replace("**", ""))
        if len(line) < 25 or line.lower() == title.lower() or re.match(r"^[\w ]{1,25}:", line):
            continue
        keep.append(line)
    out = ""
    for sent in re.split(r"(?<=[.!?])\s+", " ".join(keep)):
        if out and len(out) + len(sent) > limit:
            break
        out += sent + " "
    return out.strip()[: limit + 200]


def describe(meta: dict, text: str) -> str:
    """Offline summary: a templated line from the metadata + the opening prose."""
    head = meta["doc_type"].replace("-", " ").capitalize()
    if meta["parties"]:
        head += " involving " + ", ".join(meta["parties"][:3])
    parts = [head + "."]
    if meta["dates"]:
        parts.append("Key dates: " + "; ".join(f"{k.removesuffix('_date').replace('_', ' ')} {v}"
                                               for k, v in meta["dates"].items()) + ".")
    if meta["amounts"]:
        parts.append("Amounts: " + ", ".join(meta["amounts"][:3]) + ".")
    body = summarize(text, meta["title"])
    return " ".join(parts + ([body] if body else []))


def heuristic_metadata(text: str, filename: str) -> dict:
    category, folder = classify(text, filename)
    dates = label_dates(text)
    nd = notice_days(text)
    anchor = dates.get("expiry_date") or dates.get("renewal_date")  # notice runs back from end of term
    if nd and anchor:
        dates["notice_deadline_date"] = (dt.date.fromisoformat(anchor) - dt.timedelta(days=nd)).isoformat()
    title = title_for(text, filename)
    dtype = doc_type(text, category, filename, title)
    tags = [category] + ([dtype] if dtype != category else [])
    if "renewal_date" in dates or re.search(r"auto(?:matically)?[- ]renew", text, re.I):
        tags.append("renewal")
    meta = {
        "title": title,
        "category": category,
        "folder": folder,
        "doc_type": dtype,
        "parties": find_parties(text),
        "dates": dates,
        "amounts": find_amounts(text),
        "notice_days": nd,
        "tags": tags,
    }
    meta["summary"] = describe(meta, text) if text.strip() else f"File {Path(filename).name} (no extractable text)."
    return meta
