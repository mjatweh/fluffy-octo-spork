"""Command-line interface: python -m content_agent <command> ..."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import calendar_plan, generators, prompts, render
from .brand import (PROJECT_ROOT, copy_templates, interview, load_brand, show_brand, validate_brand)
from .llm import LLM, LLMError, has_credentials
from .output import vault_path, write_doc


def _common() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--brand", help="brand directory (default: $BRAND_DIR, ./brand, or brand/examples)")
    p.add_argument("--dry-run", action="store_true", help="offline templated output, no API calls")
    p.add_argument("--out", type=Path, help="output directory (default: ./output or $OUTPUT_DIR)")
    p.add_argument("--vault", help="Obsidian vault path (default: $VAULT_PATH)")
    p.add_argument("--no-save", action="store_true", help="print only, don't write files")
    p.add_argument("--model", help="Claude model (default: $CLAUDE_MODEL or claude-opus-5-5)")
    p.add_argument("--max-revisions", type=int, default=2, help="auto-revise passes when validation fails")
    return p


def build_parser() -> argparse.ArgumentParser:
    common = _common()
    ap = argparse.ArgumentParser(prog="content_agent", description="Brand-aware content marketing agent")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("brand", help="manage brand knowledge")
    bsub = b.add_subparsers(dest="brand_cmd", required=True)
    bi = bsub.add_parser("init", help="interview to create brand files")
    bi.add_argument("--dir", type=Path, default=PROJECT_ROOT / "brand")
    bi.add_argument("--force", action="store_true")
    bi.add_argument("--blank", action="store_true", help="copy blank templates instead of interviewing")
    for name in ("show", "validate"):
        bsub.add_parser(name, parents=[common])

    sub.add_parser("types", help="list content types")

    g = sub.add_parser("generate", parents=[common], help="generate one piece of content")
    g.add_argument("type", help=", ".join(prompts.TYPES))
    g.add_argument("--topic", required=True)
    g.add_argument("--pillar")
    g.add_argument("--offer", help="offer name from offers.md to promote")
    g.add_argument("--notes", default="", help="extra instructions")

    r = sub.add_parser("repurpose", parents=[common], help="turn one long piece into a multi-channel pack")
    r.add_argument("file", type=Path)
    r.add_argument("--channels", default=",".join(generators.REPURPOSE_DEFAULT))
    r.add_argument("--topic")

    c = sub.add_parser("calendar", parents=[common], help="plan a week/month content calendar")
    c.add_argument("--period", choices=["week", "month"], default="week")
    c.add_argument("--days", type=int, help="override period length in days")
    c.add_argument("--start", type=date.fromisoformat, help="YYYY-MM-DD (default: next Monday)")
    c.add_argument("--channels", default=",".join(calendar_plan.DEFAULT_CHANNELS))

    v = sub.add_parser("review", parents=[common], help="score a draft against brand voice & ICP")
    v.add_argument("file", nargs="?", type=Path, help="draft file ('-' for stdin)")
    v.add_argument("--text", help="draft text instead of a file")
    v.add_argument("--channel")
    return ap


def _setup(args):
    brand = load_brand(args.brand)
    errors, _ = validate_brand(brand)
    if errors:
        sys.exit(f"Brand at {brand.root} is incomplete:\n- " + "\n- ".join(errors) +
                 "\nRun: python -m content_agent brand validate")
    dry = args.dry_run
    if not dry and not has_credentials():
        print("[content_agent] ANTHROPIC_API_KEY not set — using --dry-run templates.", file=sys.stderr)
        dry = True
    return brand, (None if dry else LLM(model=args.model)), dry


def _save(args, **kw) -> list[Path]:
    if args.no_save:
        return []
    return write_doc(out_dir=args.out, vault=vault_path(args.vault), **kw)


def _emit_result(args, res: generators.Result, brand) -> None:
    md = render.to_markdown(res.content)
    extra = {".html": render.newsletter_html(res.content)} if res.key == "newsletter" else None
    notes = ""
    if res.issues:
        notes = "\n> **Validation warnings:**\n" + "".join(f"> - {i}\n" for i in res.issues)
    paths = _save(args, kind=res.type.category, channel=res.key, topic=res.topic,
                  title=f"{res.type.label}: {res.topic}", body=md + notes, extra=extra,
                  meta={"brand": brand.name, "dry_run": res.dry_run, "revisions": res.revisions})
    print(f"\n===== {res.type.label} =====\n\n{md}")
    for i in res.issues:
        print(f"[warning] {i}", file=sys.stderr)
    for p in paths:
        print(f"[saved] {p}", file=sys.stderr)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (LLMError, KeyError, FileNotFoundError, FileExistsError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _dispatch(args) -> int:
    if args.cmd == "types":
        for ct in prompts.TYPES.values():
            print(f"{ct.key:14} {ct.label:22} [{ct.category}]")
        return 0

    if args.cmd == "brand":
        if args.brand_cmd == "init":
            path = copy_templates(args.dir, args.force) if args.blank else interview(args.dir, force=args.force)
            print(f"Brand files ready in {path}")
            return 0
        brand = load_brand(args.brand)
        if args.brand_cmd == "show":
            print(show_brand(brand))
            return 0
        errors, warnings = validate_brand(brand)
        for w in warnings:
            print(f"warning: {w}")
        for e in errors:
            print(f"error: {e}")
        print(f"{brand.root}: " + ("INVALID" if errors else "OK"))
        return 1 if errors else 0

    brand, llm, dry = _setup(args)

    if args.cmd == "generate":
        res = generators.generate(args.type, args.topic, brand, llm, dry_run=dry, notes=args.notes,
                                  pillar=args.pillar, offer=args.offer, max_revisions=args.max_revisions)
        _emit_result(args, res, brand)
        return 0

    if args.cmd == "repurpose":
        source = args.file.read_text(encoding="utf-8")
        channels = [c.strip() for c in args.channels.split(",") if c.strip()]
        for res in generators.repurpose(source, brand, llm, channels=channels, topic=args.topic,
                                        dry_run=dry, max_revisions=args.max_revisions):
            _emit_result(args, res, brand)
        return 0

    if args.cmd == "calendar":
        channels = [c.strip() for c in args.channels.split(",") if c.strip()]
        entries = calendar_plan.build_calendar(brand, llm, start=args.start, period=args.period,
                                               days=args.days, channels=channels, dry_run=dry)
        md = calendar_plan.to_markdown(entries, brand)
        topic = f"{args.period} of {entries[0].date}" if entries else args.period
        paths = _save(args, kind="calendar", channel="multi", topic=topic, title=f"Content calendar: {topic}",
                      body=md.split("\n", 2)[2], extra={".csv": calendar_plan.to_csv(entries)},
                      meta={"brand": brand.name, "dry_run": dry})
        print(md)
        for p in paths:
            print(f"[saved] {p}", file=sys.stderr)
        return 0

    if args.cmd == "review":
        if args.text:
            draft = args.text
        elif args.file and str(args.file) != "-":
            draft = args.file.read_text(encoding="utf-8")
        else:
            draft = sys.stdin.read()
        rev = generators.review(draft, brand, llm, channel=args.channel, dry_run=dry)
        md = render.to_markdown(rev)
        topic = (args.file.stem if args.file and str(args.file) != "-" else draft.strip().split("\n")[0][:60])
        paths = _save(args, kind="review", channel=args.channel or "review", topic=topic,
                      title=f"Brand voice review: {topic}", body=md,
                      meta={"brand": brand.name, "dry_run": dry, "score": rev.overall_score})
        print(md)
        for p in paths:
            print(f"[saved] {p}", file=sys.stderr)
        return 0
    return 1
