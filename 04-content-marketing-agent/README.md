# Content Marketing Agent

An AI agent that knows your **brand** and **ideal customer profile (ICP)** and uses them to write
social posts, email newsletters and marketing assets. It runs on Claude through the Anthropic Python SDK. With no API key it falls back to a deterministic offline `--dry-run` mode.

```
brand/*.md ──► brand context (prompt-cached) ─┐
                                              ├─► Claude structured output (JSON schema)
channel brief + constraints + topic ──────────┘          │
                                                         ▼
                        dataclass ◄── parse ◄── JSON ── validate (lengths, counts, banned words)
                            │                                 │ fails? send issues back ─► revise (≤2x)
                            ▼                                 ▼
             output/<type>/YYYY-MM-DD-<slug>.md (+ .html / .csv)   +   $VAULT_PATH/Content/Drafts/<type>/
```

## Setup

```bash
cd 04-content-marketing-agent
pip install -r requirements.txt          # anthropic>=1.11, pytest
cp .env.example .env                     # add ANTHROPIC_API_KEY (optional)
python -m content_agent brand validate   # checks the example brand
python -m pytest -q                      # no network or key needed
```

| Env var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | Claude key. If it isn't set, every command runs in dry-run mode. |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Model override (`--model` also works) |
| `CLAUDE_EFFORT` | `medium` | `low` / `medium` / `high` / `xhigh` / `max` |
| `CLAUDE_FALLBACKS` | `1` | Server-side refusal fallback (`fallbacks: "default"`) on supported models. Set it to `0` to turn it off. |
| `BRAND_DIR` | `./brand`, or `brand/examples` if `./brand` is empty | Brand knowledge directory (`--brand` also works) |
| `OUTPUT_DIR` | `./output` | Where drafts are written (`--out` also works) |
| `VAULT_PATH` | – | Obsidian vault (Second Brain, project 02) (`--vault` also works) |

## 1. Fill in your brand and ICP

The agent reads four markdown files. Each `## Heading` is a section. Text inside HTML comments is guidance and is ignored.

| File | Sections |
|---|---|
| `brand.md` | Business Name, Mission, Offer, Voice & Tone, Words We Use, **Words We Avoid** (banned and enforced), Example Posts (separated by `---`) |
| `icp.md` | Who They Are, Pains, Desires, Objections, Where They Hang Out, Language They Use |
| `offers.md` | One `## Offer name` section per product, with price, outcome and CTA link |
| `content_pillars.md` | 3-5 `## Pillar` sections: a description plus bullet example topics (the calendar rotates through these) |

There are three ways to get started:

```bash
python -m content_agent brand init                 # interview on stdin -> writes brand/*.md
python -m content_agent brand init --blank         # copy blank templates (brand/templates/) to brand/
cp brand/examples/*.md brand/                       # start from the filled-in example and edit
```

The example in `brand/examples/` is **Northbeam AI**, a fictional AI-automation consultancy that serves 10-100 person agencies and accounting firms. Until `brand/brand.md` exists, commands use this example.

```bash
python -m content_agent brand show       # summary: voice, banned words, ICP, offers, pillars
python -m content_agent brand validate   # errors for missing/TODO sections, warnings for thin ones
```

Banned words are matched as whole words, ignoring case, and simple inflections are caught too (`leverage` also matches `leveraging`). A reason after an em dash is optional: `- leverage — say "use"`. The `review` command uses a `say "X"` reason as the replacement word.

## 2. Generate content

```bash
python -m content_agent types            # list content types
```

### Social posts
```bash
python -m content_agent generate linkedin  --topic "Why your ChatGPT pilot failed"
python -m content_agent generate x         --topic "AI won't replace your team; a broken process will"
python -m content_agent generate x-thread  --topic "5 admin tasks every agency can automate" --pillar "Boring Work, Automated"
python -m content_agent generate instagram --topic "When NOT to use AI"          # caption + hashtags + carousel outline
python -m content_agent generate tiktok    --topic "The 20-minute weekly ops review"  # hook / body / CTA + shot list
```

### Email newsletter
```bash
python -m content_agent generate newsletter --topic "Keeping client data safe with AI" --offer "AI Ops Audit"
# -> output/newsletter/<date>-<slug>.md   (3-5 subject lines, preview text, markdown body)
#    output/newsletter/<date>-<slug>.html (simple table-based email HTML)
```

### Marketing assets
```bash
python -m content_agent generate landing-page --topic "AI Ops Audit" --offer "AI Ops Audit"
python -m content_agent generate ads          --topic "Win back 10 hours per person per month"
python -m content_agent generate blog-outline --topic "How to get processes out of the founder's head"
```

Options that work with every generator: `--notes "extra instructions"`, `--pillar`, `--offer`, `--dry-run`,
`--no-save` (print only), `--out DIR`, `--vault DIR`, `--brand DIR`, `--model`, `--max-revisions N`.

### Repurpose one long piece into a multi-channel pack
```bash
python -m content_agent repurpose samples/long-article.md
python -m content_agent repurpose talk-transcript.md --channels linkedin,x-thread,newsletter --topic "Onboarding automation"
```

### Content calendar (CSV + markdown)
```bash
python -m content_agent calendar                          # next Monday, 1 week
python -m content_agent calendar --period month --start 2026-11-02 --channels linkedin,x,newsletter
```
The code lays out the dated slots: each channel has a posting cadence (for example LinkedIn Mon/Wed/Fri and the newsletter on Thursday), and pillars rotate across the slots. Claude then fills in a topic, hook and CTA for each slot. The CSV columns are `date, weekday, channel, pillar, topic, hook, cta, status`.

### Brand-voice review
```bash
python -m content_agent review samples/draft-post.md --channel linkedin
pbpaste | python -m content_agent review -          # or --text "..."
```
The output gives an overall score, a voice score and an ICP-fit score (each 0-100), plus strengths, issues, line edits and a revised draft. In dry-run mode the score comes from a heuristic: banned and preferred words, ICP vocabulary, sentence length and whether the draft addresses the reader as "you".

## Channel constraints (validated, with an automatic revise pass)

| Type | Enforced |
|---|---|
| LinkedIn | hook ≤ 210 chars, post ≤ 3000, 3-5 hashtags |
| X post | ≤ 280 chars (URLs count as 23), ≤ 2 hashtags |
| X thread | 3-12 tweets, **each** ≤ 280 chars |
| Instagram | caption + tags ≤ 2200, 5-15 hashtags, 3-10 slides, slide titles ≤ 60 |
| TikTok/Reels | hook ≤ 120 chars, 15-90 s, spoken words ≤ 3 × seconds, ≥ 3 shots |
| Newsletter | 3-5 subject lines ≤ 60 chars, preview ≤ 140, 2-5 sections |
| Landing page | headline ≤ 80, sub ≤ 200, CTA ≤ 40, 3-6 benefits, 4-8 FAQs, social proof must be `[placeholders]` |
| Ads | 3-5 variants; headline ≤ 40, primary text ≤ 125, description ≤ 30 |
| Blog outline | title ≤ 70, meta ≤ 160, 4-10 sections × 2-5 points |
| All | no empty fields, no banned words |

If validation fails, the issue list goes back to Claude in the same conversation for up to `--max-revisions` passes (default 2). If issues remain after that, hard limits are enforced: tweets are trimmed at a word boundary and lists are truncated. Anything left over is written as a warning into the draft.

## How Claude is used

- The model is `claude-opus-5-5` with `output_config.format` (a JSON schema). The schema is generated from the output dataclasses in `content_agent/schemas.py`, so the prompt, the parser and the validators share one definition. The parser also accepts `tool_use` blocks.
- **Prompt caching:** the system prompt is split into stable instructions plus the full brand knowledge block, and the brand block carries a `cache_control` breakpoint. Every generation, revision and repurpose channel in a session reuses the cached brand context.
- Refusals (`stop_reason: "refusal"`) and truncation are surfaced as errors. On Opus 5.5, Opus 5, Sonnet 5.5 and Fable 5.1, server-side `fallbacks: "default"` is enabled. Set `CLAUDE_FALLBACKS=0` to disable it.
- The system prompt forbids invented stats and testimonials, so Claude uses `[placeholders]` instead.

## Second Brain (Obsidian) integration

When `VAULT_PATH` is set (or you pass `--vault`), every draft is also saved as a note at
`<vault>/Content/Drafts/<type>/YYYY-MM-DD-<slug>.md` (the Second Brain vault's drafts folder). `<type>` is one of `social`, `newsletter`, `assets`, `calendar` or `review`. Each note has YAML frontmatter:

```yaml
---
type: "social"
channel: "linkedin"
status: "draft"
topic: "Why your ChatGPT pilot failed"
created: "2026-10-03"
brand: "Northbeam AI"
dry_run: false
revisions: 0
tags: ["content", "social", "linkedin"]
---
```

## Layout

```
content_agent/
  cli.py            argparse commands (brand / types / generate / repurpose / calendar / review)
  brand.py          load/parse/validate brand files, `brand init` interview
  schemas.py        output dataclasses -> JSON schema, dict -> dataclass parsing
  prompts.py        content-type registry (brief + constraints), prompt assembly
  llm.py            Anthropic client wrapper (structured outputs, caching, fallbacks)
  generators.py     generate -> validate -> revise loop, repurpose, review
  validators.py     per-channel limits, banned words, hard enforcement
  calendar_plan.py  slot layout, calendar fill, CSV/markdown
  dryrun.py         deterministic offline templates + heuristic review
  render.py         markdown renderers, minimal markdown->HTML, newsletter email HTML
  output.py         output/ + vault writer with frontmatter
brand/examples/     filled-in example brand (Northbeam AI)
brand/templates/    blank templates
samples/            long-form article and a hype-y draft for repurpose/review demos
tests/              pytest suite (mocked client, no network)
```
