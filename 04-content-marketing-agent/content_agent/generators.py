"""Generation pipeline: prompt -> structured JSON -> dataclass -> validate -> revise (-> enforce)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import dryrun, prompts, schemas as s
from .brand import Brand
from .llm import LLM
from .validators import enforce, normalize, validate

REPURPOSE_DEFAULT = ("linkedin", "x-thread", "instagram", "tiktok", "newsletter")


@dataclass
class Result:
    key: str
    topic: str
    content: object
    issues: list[str] = field(default_factory=list)
    revisions: int = 0
    dry_run: bool = False

    @property
    def type(self) -> prompts.ContentType:
        return prompts.get_type(self.key)


def _structured(llm: LLM, brand: Brand, cls, prompt: str, max_revisions: int, check) -> tuple[object, list[str], int]:
    """Ask Claude for `cls`-shaped JSON; on validation failure, send the issues back for a revise pass."""
    schema = s.schema_for(cls)
    messages = [{"role": "user", "content": prompt}]
    context = brand.context()
    revisions = 0
    while True:
        data = llm.generate_json(prompts.SYSTEM, context, messages, schema)
        try:
            obj = normalize(s.from_dict(cls, data))
            issues = check(obj)
        except ValueError as e:
            obj, issues = None, [f"output did not match schema: {e}"]
        if not issues or revisions >= max_revisions:
            if obj is None:
                raise ValueError(issues[0])
            return obj, issues, revisions
        revisions += 1
        messages += [{"role": "assistant", "content": json.dumps(data)},
                     {"role": "user", "content": prompts.build_revision_prompt(issues)}]


def generate(key: str, topic: str, brand: Brand, llm: LLM | None = None, *, dry_run: bool = False,
             notes: str = "", source: str = "", pillar: str | None = None, offer: str | None = None,
             max_revisions: int = 2) -> Result:
    ct = prompts.get_type(key)
    check = lambda o: validate(o, brand.banned_words)  # noqa: E731
    if dry_run:
        obj = normalize(dryrun.build(ct.key, brand, topic, source=source, offer=offer, pillar=pillar))
        issues, revisions = check(obj), 0
    else:
        prompt = prompts.build_prompt(ct, topic, notes=notes, source=source, pillar=pillar, offer=offer)
        obj, issues, revisions = _structured(llm or LLM(), brand, ct.cls, prompt, max_revisions, check)
    if issues:  # revisions exhausted: hard-enforce what can be enforced, report the rest
        obj = enforce(obj)
        issues = check(obj)
    return Result(ct.key, topic, obj, issues, revisions, dry_run)


def repurpose(source: str, brand: Brand, llm: LLM | None = None, *, channels=REPURPOSE_DEFAULT,
              topic: str | None = None, dry_run: bool = False, **kw) -> list[Result]:
    topic = topic or _guess_topic(source)
    return [generate(c, topic, brand, llm, dry_run=dry_run, source=source, **kw) for c in channels]


def _guess_topic(source: str) -> str:
    for line in source.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:100]
    return "Repurposed content"


def review(draft: str, brand: Brand, llm: LLM | None = None, *, channel: str | None = None,
           dry_run: bool = False) -> s.Review:
    if dry_run:
        return dryrun.review(brand, draft)
    obj, _, _ = _structured(llm or LLM(), brand, s.Review, prompts.review_prompt(draft, channel), 1, validate)
    return obj
