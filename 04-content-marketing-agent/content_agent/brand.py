"""Brand knowledge: load, validate and interview for the brand/ICP markdown files."""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRAND_FILES = ("brand.md", "icp.md", "offers.md", "content_pillars.md")
REQUIRED_SECTIONS = {
    "brand.md": ["Business Name", "Mission", "Offer", "Voice & Tone", "Words We Use",
                 "Words We Avoid", "Example Posts"],
    "icp.md": ["Who They Are", "Pains", "Desires", "Objections", "Where They Hang Out",
               "Language They Use"],
}
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")


def parse_sections(text: str) -> dict[str, str]:
    """Split markdown into {"## heading": body}; HTML comments (template guidance) are dropped."""
    sections: dict[str, str] = {}
    current, buf = None, []
    for line in _COMMENT.sub("", text).splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current, buf = line[3:].strip(), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def bullets(text: str) -> list[str]:
    return [m.group(1).strip() for line in text.splitlines() if (m := _BULLET.match(line))]


def _is_placeholder(text: str) -> bool:
    return not text.strip() or "TODO" in text


@dataclass
class Pillar:
    name: str
    description: str
    topics: list[str] = field(default_factory=list)


@dataclass
class Brand:
    root: Path
    files: dict[str, str]
    sections: dict[str, dict[str, str]]

    def section(self, file: str, name: str) -> str:
        for key, value in self.sections.get(file, {}).items():
            if key.lower() == name.lower():
                return value
        return ""

    def _list(self, file: str, name: str) -> list[str]:
        text = self.section(file, name)
        return bullets(text) or ([text] if text and not _is_placeholder(text) else [])

    name = property(lambda self: self.section("brand.md", "Business Name").splitlines()[0]
                    if self.section("brand.md", "Business Name") else "Your Brand")
    mission = property(lambda self: self.section("brand.md", "Mission"))
    offer = property(lambda self: self.section("brand.md", "Offer"))
    voice = property(lambda self: self._list("brand.md", "Voice & Tone"))
    do_words = property(lambda self: self._list("brand.md", "Words We Use"))
    who = property(lambda self: self.section("icp.md", "Who They Are"))
    pains = property(lambda self: self._list("icp.md", "Pains"))
    desires = property(lambda self: self._list("icp.md", "Desires"))
    objections = property(lambda self: self._list("icp.md", "Objections"))
    hangouts = property(lambda self: self._list("icp.md", "Where They Hang Out"))
    language = property(lambda self: self._list("icp.md", "Language They Use"))

    @property
    def banned_map(self) -> dict[str, str]:
        """{word: reason} from "Words We Avoid"; anything after an em/en dash or colon is the reason."""
        out = {}
        for item in self._list("brand.md", "Words We Avoid"):
            word, *reason = re.split(r"\s+[—–]\s+|\s+-\s+|:\s|\s\(", item, maxsplit=1)
            word = word.strip().strip("\"'`").strip()
            if word and not _is_placeholder(word):
                out[word.lower()] = reason[0].strip(" )") if reason else ""
        return out

    @property
    def banned_words(self) -> list[str]:
        return list(self.banned_map)

    @property
    def example_posts(self) -> list[str]:
        text = self.section("brand.md", "Example Posts")
        return [p.strip() for p in re.split(r"^\s*---\s*$", text, flags=re.M) if p.strip()]

    @property
    def offers(self) -> dict[str, str]:
        return {k: v for k, v in self.sections.get("offers.md", {}).items() if not _is_placeholder(k + v)}

    @property
    def pillars(self) -> list[Pillar]:
        out = []
        for name, body in self.sections.get("content_pillars.md", {}).items():
            if _is_placeholder(name + body):
                continue
            desc = "\n".join(l for l in body.splitlines() if l.strip() and not _BULLET.match(l)).strip()
            out.append(Pillar(name, desc, bullets(body)))
        return out

    def context(self) -> str:
        """The full brand knowledge block sent to Claude (stable => prompt-cacheable)."""
        parts = [f"<brand_knowledge business=\"{self.name}\">"]
        for fname in BRAND_FILES:
            body = _COMMENT.sub("", self.files.get(fname, "")).strip()
            parts.append(f"<file name=\"{fname}\">\n{body}\n</file>")
        if self.banned_words:
            parts.append("<banned_words>" + ", ".join(self.banned_words) + "</banned_words>")
        parts.append("</brand_knowledge>")
        return "\n\n".join(parts)


def resolve_brand_dir(arg: str | os.PathLike | None = None) -> Path:
    """--brand arg > $BRAND_DIR > ./brand (if filled in) > bundled example brand."""
    if arg:
        return Path(arg)
    if os.environ.get("BRAND_DIR"):
        return Path(os.environ["BRAND_DIR"])
    default = PROJECT_ROOT / "brand"
    if (default / "brand.md").exists():
        return default
    return default / "examples"


def load_brand(path: str | os.PathLike | None = None) -> Brand:
    root = resolve_brand_dir(path)
    if not root.is_dir():
        raise FileNotFoundError(f"Brand directory not found: {root}")
    files = {f: (root / f).read_text(encoding="utf-8") for f in BRAND_FILES if (root / f).exists()}
    return Brand(root, files, {f: parse_sections(t) for f, t in files.items()})


def validate_brand(brand: Brand) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors, warnings = [], []
    for fname in BRAND_FILES:
        if fname not in brand.files:
            errors.append(f"missing file: {fname}")
    for fname, names in REQUIRED_SECTIONS.items():
        if fname not in brand.files:
            continue
        for name in names:
            text = brand.section(fname, name)
            if _is_placeholder(text):
                errors.append(f"{fname}: section '## {name}' is missing or still TODO")
    if "offers.md" in brand.files and not brand.offers:
        errors.append("offers.md: add at least one '## Offer name' section")
    if "content_pillars.md" in brand.files:
        if not brand.pillars:
            errors.append("content_pillars.md: add at least one '## Pillar name' section")
        elif len(brand.pillars) < 3:
            warnings.append("content_pillars.md: 3-5 pillars recommended")
        for p in brand.pillars:
            if not p.topics:
                warnings.append(f"content_pillars.md: pillar '{p.name}' has no example topic bullets")
    if brand.files.get("icp.md") and 0 < len(brand.pains) < 3:
        warnings.append("icp.md: list at least 3 pains")
    if brand.files.get("brand.md") and not brand.banned_words:
        warnings.append("brand.md: no banned words; add some under '## Words We Avoid'")
    if brand.files.get("brand.md") and len(brand.example_posts) < 2:
        warnings.append("brand.md: 2+ example posts (separated by ---) help the voice match")
    return errors, warnings


def show_brand(brand: Brand) -> str:
    lines = [f"Brand: {brand.name}  ({brand.root})", "", f"Mission: {brand.mission}", "",
             "Voice: " + "; ".join(brand.voice), "Use: " + ", ".join(brand.do_words),
             "Avoid: " + ", ".join(brand.banned_words), "", f"ICP: {brand.who}",
             "Pains: " + "; ".join(brand.pains), "Desires: " + "; ".join(brand.desires),
             "Objections: " + "; ".join(brand.objections),
             "Hangs out: " + ", ".join(brand.hangouts), "",
             "Offers: " + ", ".join(brand.offers), "Pillars:"]
    lines += [f"  - {p.name} ({len(p.topics)} topics)" for p in brand.pillars]
    return "\n".join(lines)


# ---------------------------------------------------------------- interview
# (file, section, question, is_list)
QUESTIONS = [
    ("brand.md", "Business Name", "What is your business called?", False),
    ("brand.md", "Mission", "In 1-2 sentences: who do you help, and what change do you create?", False),
    ("brand.md", "Offer", "What do you sell? (one paragraph)", False),
    ("brand.md", "Voice & Tone", "Describe your voice (comma-separated, e.g. direct, warm, no hype)", True),
    ("brand.md", "Words We Use", "Words/phrases that sound like you (comma-separated)", True),
    ("brand.md", "Words We Avoid", "Words you never want to see in your content (comma-separated)", True),
    ("brand.md", "Example Posts", "Paste one past post that sounds like you (single line, '|' separates posts)", False),
    ("icp.md", "Who They Are", "Who is your ideal customer? (role, company, size, budget)", False),
    ("icp.md", "Pains", "Their top pains (comma-separated)", True),
    ("icp.md", "Desires", "What outcomes do they want? (comma-separated)", True),
    ("icp.md", "Objections", "Why do they hesitate to buy? (comma-separated)", True),
    ("icp.md", "Where They Hang Out", "Where do they spend time online/offline? (comma-separated)", True),
    ("icp.md", "Language They Use", "Exact phrases they use about their problem (comma-separated)", True),
]


def interview(target: Path, ask: Callable[[str], str] = input, say: Callable[[str], None] = print,
              force: bool = False) -> Path:
    """Ask questions on stdin and write the four brand files into `target`."""
    target = Path(target)
    if (target / "brand.md").exists() and not force:
        raise FileExistsError(f"{target}/brand.md exists; use --force to overwrite")
    say("Let's capture your brand and ideal customer. Press Enter to skip a question.\n")
    answers: dict[str, list[tuple[str, str]]] = {"brand.md": [], "icp.md": []}
    for fname, section, question, is_list in QUESTIONS:
        raw = ask(f"{question}\n> ").strip()
        if not raw:
            body = "TODO"
        elif is_list:
            body = "\n".join(f"- {x.strip()}" for x in raw.split(",") if x.strip())
        elif section == "Example Posts":
            body = "\n---\n".join(p.strip() for p in raw.split("|") if p.strip())
        else:
            body = raw
        answers[fname].append((section, body))
    offer_name = ask("Name of your main offer/product?\n> ").strip() or "TODO Offer Name"
    offer_desc = ask("Describe it: who it's for, outcome, price, CTA link\n> ").strip() or "TODO"
    pillars = ask("3-5 content pillars/themes you want to be known for (comma-separated)\n> ").strip()

    target.mkdir(parents=True, exist_ok=True)
    titles = {"brand.md": "Brand", "icp.md": "Ideal Customer Profile"}
    for fname, items in answers.items():
        body = "\n\n".join(f"## {s}\n{b}" for s, b in items)
        (target / fname).write_text(f"# {titles[fname]}\n\n{body}\n", encoding="utf-8")
    (target / "offers.md").write_text(f"# Offers\n\n## {offer_name}\n{offer_desc}\n", encoding="utf-8")
    pillar_md = "\n\n".join(f"## {p.strip()}\nWhat this pillar covers and why the ICP cares.\n- Example topic"
                            for p in pillars.split(",") if p.strip()) or "## TODO Pillar Name\nTODO"
    (target / "content_pillars.md").write_text(f"# Content Pillars\n\n{pillar_md}\n", encoding="utf-8")
    say(f"\nSaved brand files to {target}. Edit them any time, then run: python -m content_agent brand validate")
    return target


def copy_templates(target: Path, force: bool = False) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    for fname in BRAND_FILES:
        dest = target / fname
        if dest.exists() and not force:
            raise FileExistsError(f"{dest} exists; use --force to overwrite")
        shutil.copy(PROJECT_ROOT / "brand" / "templates" / fname, dest)
    return target
