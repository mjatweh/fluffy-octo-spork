"""Render content dataclasses to markdown (and the newsletter to simple HTML)."""
from __future__ import annotations

import html
import re

from . import schemas as s
from .validators import x_length


def _tags(tags):
    return " ".join("#" + t for t in tags)


def md_linkedin(p: s.LinkedInPost):
    return f"{p.hook}\n\n{p.body}\n\n{p.cta}\n\n{_tags(p.hashtags)}\n"


def md_x(p: s.XPost):
    return f"{p.text}\n\n_{x_length(p.text)}/280 characters_\n"


def md_x_thread(p: s.XThread):
    return "\n\n---\n\n".join(f"{t}\n\n_{x_length(t)}/280_" for t in p.tweets) + "\n"


def md_instagram(p: s.InstagramPost):
    slides = "\n".join(f"{i}. **{sl.title}** — {sl.body}  \n   _Visual:_ {sl.visual}"
                       for i, sl in enumerate(p.slides, 1))
    return f"## Caption\n\n{p.caption}\n\n{_tags(p.hashtags)}\n\n## Carousel outline\n\n{slides}\n"


def md_tiktok(p: s.VideoScript):
    beats = "\n".join(f"- {b}" for b in p.body)
    rows = "\n".join(f"| {x.timestamp} | {x.visual} | {x.voiceover} | {x.on_screen_text} |" for x in p.shots)
    return (f"**Target length:** {p.duration_seconds}s\n\n## Hook\n\n{p.hook}\n\n## Body\n\n{beats}\n\n"
            f"## CTA\n\n{p.cta}\n\n## Shot list\n\n| Time | Visual | Voiceover | On-screen text |\n"
            f"|---|---|---|---|\n{rows}\n")


def md_newsletter(p: s.Newsletter):
    subjects = "\n".join(f"{i}. {x}" for i, x in enumerate(p.subject_lines, 1))
    body = "\n\n".join(f"## {sec.heading}\n\n{sec.body_markdown}" for sec in p.sections)
    return (f"**Subject line variants:**\n\n{subjects}\n\n**Preview text:** {p.preview_text}\n\n---\n\n"
            f"# {p.title}\n\n{body}\n\n**[{p.cta_text}]({p.cta_url})**\n\n{p.sign_off}\n")


def md_landing_page(p: s.LandingPage):
    benefits = "\n".join(f"- **{b.title}** — {b.description}" for b in p.benefits)
    proof = "\n".join(f"- {x}" for x in p.social_proof)
    faq = "\n\n".join(f"**{f.question}**  \n{f.answer}" for f in p.faq)
    return (f"## Hero\n\n# {p.hero_headline}\n\n{p.hero_subheadline}\n\n**[{p.primary_cta}]**\n\n"
            f"## Benefits\n\n{benefits}\n\n## Social proof\n\n{proof}\n\n## FAQ\n\n{faq}\n\n"
            f"## Final CTA\n\n{p.final_cta}\n")


def md_ads(p: s.AdCopy):
    return "\n".join(f"## Variant {i}: {v.angle}\n\n- **Headline** ({len(v.headline)}/40): {v.headline}\n"
                     f"- **Primary text** ({len(v.primary_text)}/125): {v.primary_text}\n"
                     f"- **Description** ({len(v.description)}/30): {v.description}\n"
                     for i, v in enumerate(p.variants, 1))


def md_blog_outline(p: s.BlogOutline):
    secs = "\n\n".join(f"## {x.heading}\n\n" + "\n".join(f"- {pt}" for pt in x.points) for x in p.sections)
    return (f"# {p.title}\n\n**Target keyword:** {p.target_keyword}  \n**Meta description:** "
            f"{p.meta_description}\n\n**Intro:** {p.intro}\n\n{secs}\n\n**CTA:** {p.cta}\n")


def md_review(p: s.Review):
    li = lambda xs: "\n".join(f"- {x}" for x in xs) or "- (none)"  # noqa: E731
    edits = "\n".join(f"- ~~{e.original}~~ → **{e.suggestion}** — {e.reason}" for e in p.suggested_edits) or "- (none)"
    return (f"**Overall:** {p.overall_score}/100 · **Voice:** {p.voice_score}/100 · **ICP fit:** {p.icp_score}/100\n\n"
            f"{p.summary}\n\n## Strengths\n\n{li(p.strengths)}\n\n## Issues\n\n{li(p.issues)}\n\n"
            f"## Suggested edits\n\n{edits}\n\n## Revised draft\n\n{p.revised_draft}\n")


RENDERERS = {s.LinkedInPost: md_linkedin, s.XPost: md_x, s.XThread: md_x_thread, s.InstagramPost: md_instagram,
             s.VideoScript: md_tiktok, s.Newsletter: md_newsletter, s.LandingPage: md_landing_page,
             s.AdCopy: md_ads, s.BlogOutline: md_blog_outline, s.Review: md_review}


def to_markdown(obj) -> str:
    return RENDERERS[type(obj)](obj)


# ------------------------------------------------------------------ minimal markdown -> HTML
def _inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])[*_](?!\s)(.+?)(?<!\s)[*_](?![\w*])", r"<em>\1</em>", t)
    return t


def md_to_html(md: str) -> str:
    out, para, lst = [], [], None

    def flush():
        nonlocal para, lst
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para = []
        if lst:
            out.append(f"<{lst[0]}>" + "".join(f"<li>{_inline(i)}</li>" for i in lst[1]) + f"</{lst[0]}>")
            lst = None

    for line in md.splitlines():
        stripped = line.strip()
        if m := re.match(r"(#{1,4})\s+(.*)", stripped):
            flush()
            n = len(m.group(1)) + 1
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        elif m := re.match(r"([-*+]|\d+[.)])\s+(.*)", stripped):
            kind = "ol" if m.group(1)[0].isdigit() else "ul"
            if para or (lst and lst[0] != kind):
                flush()
            lst = lst or (kind, [])
            lst[1].append(m.group(2))
        elif not stripped:
            flush()
        else:
            if lst:
                flush()
            para.append(stripped)
    flush()
    return "\n".join(out)


def newsletter_html(p: s.Newsletter) -> str:
    body = "\n".join(f"<h2>{_inline(sec.heading)}</h2>\n{md_to_html(sec.body_markdown)}" for sec in p.sections)
    sign = "<br>".join(_inline(x) for x in p.sign_off.splitlines())
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(p.subject_lines[0] if p.subject_lines else p.title)}</title></head>
<body style="margin:0;padding:0;background:#f4f4f5;">
<span style="display:none;max-height:0;overflow:hidden;">{html.escape(p.preview_text)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:8px;">
<tr><td style="padding:32px;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.6;color:#1f2937;">
<h1 style="font-size:26px;line-height:1.3;margin:0 0 16px;">{_inline(p.title)}</h1>
{body}
<p style="text-align:center;margin:32px 0;"><a href="{html.escape(p.cta_url)}" style="background:#111827;color:#ffffff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block;">{_inline(p.cta_text)}</a></p>
<p>{sign}</p>
</td></tr></table></td></tr></table>
</body></html>
"""
