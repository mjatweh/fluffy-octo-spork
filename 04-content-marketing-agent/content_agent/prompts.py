"""Content-type registry and prompt assembly."""
from __future__ import annotations

from dataclasses import dataclass

from . import schemas as s

SYSTEM = """You are the in-house content marketer for the business described in <brand_knowledge>.
You write like the brand (match its voice & tone and example posts), for its ideal customer profile (ICP):
speak to their pains and desires in the exact language they use, pre-empt their objections, and point to
the brand's real offers. Never use words listed under "Words We Avoid" / <banned_words>, in any form.
Never invent statistics, client names, testimonials or results that are not in the brand knowledge; use
[bracketed placeholders] instead. Respond only with JSON matching the requested schema."""


@dataclass(frozen=True)
class ContentType:
    key: str
    label: str
    category: str  # social | newsletter | assets (also the output sub-folder)
    cls: type
    brief: str
    constraints: tuple[str, ...]


TYPES: dict[str, ContentType] = {t.key: t for t in [
    ContentType("linkedin", "LinkedIn post", "social", s.LinkedInPost,
                "Write a LinkedIn post. Strong 1-2 line hook, then a short story or insight, then a CTA.",
                ("hook <= 210 characters (what shows before 'see more')",
                 "whole post <= 3000 characters", "short paragraphs, plain text, no markdown",
                 "3-5 hashtags, no # symbol in the list")),
    ContentType("x", "X/Twitter post", "social", s.XPost,
                "Write a single standalone X (Twitter) post.",
                ("<= 280 characters total (URLs count as 23)", "at most 2 hashtags",
                 "no thread markers")),
    ContentType("x-thread", "X/Twitter thread", "social", s.XThread,
                "Write an X (Twitter) thread: tweet 1 is a hook that earns the click, each tweet stands alone, the last tweet is a CTA.",
                ("3-12 tweets", "EVERY tweet <= 280 characters including any '1/' numbering",
                 "at most 1 hashtag per tweet")),
    ContentType("instagram", "Instagram carousel", "social", s.InstagramPost,
                "Write an Instagram carousel post: caption, hashtags and a slide-by-slide outline.",
                ("caption + hashtags <= 2200 characters", "5-15 hashtags, no # symbol in the list",
                 "3-10 slides; slide titles <= 60 characters; slide 1 is the hook, last slide is the CTA")),
    ContentType("tiktok", "TikTok/Reels script", "social", s.VideoScript,
                "Write a short-form vertical video script (TikTok / Instagram Reels / YouTube Shorts) with a shot list.",
                ("spoken hook <= 120 characters and lands in the first 3 seconds",
                 "duration 15-90 seconds; total spoken words <= 3 x duration_seconds",
                 "3+ shots with timestamps that cover the full duration", "end with a clear spoken CTA")),
    ContentType("newsletter", "Email newsletter", "newsletter", s.Newsletter,
                "Write an email newsletter issue. One clear idea, skimmable, one primary CTA to a real offer.",
                ("3-5 subject line variants, each <= 60 characters, testing different angles",
                 "preview_text <= 140 characters and does not repeat the subject",
                 "2-5 sections in markdown", "cta_url must come from offers.md if a URL is given there")),
    ContentType("landing-page", "Landing page copy", "assets", s.LandingPage,
                "Write landing page copy for the offer: hero, benefits, social proof placeholders, FAQ, CTA.",
                ("hero headline <= 80 characters; subheadline <= 200", "primary CTA button <= 40 characters",
                 "3-6 benefits", "2-4 social proof entries that are [bracketed placeholders] only",
                 "4-8 FAQs that answer the ICP's objections")),
    ContentType("ads", "Ad copy variants", "assets", s.AdCopy,
                "Write paid social ad copy variants (Meta/LinkedIn format), each testing a different angle.",
                ("3-5 variants", "headline <= 40 characters", "primary_text <= 125 characters",
                 "description <= 30 characters")),
    ContentType("blog-outline", "Blog post outline", "assets", s.BlogOutline,
                "Write an SEO-aware blog post outline.",
                ("title <= 70 characters", "meta_description <= 160 characters",
                 "4-10 sections with 2-5 points each")),
]}

ALIASES = {"twitter": "x", "thread": "x-thread", "reels": "tiktok", "video": "tiktok", "email": "newsletter",
           "landing": "landing-page", "ad": "ads", "blog": "blog-outline"}


def get_type(key: str) -> ContentType:
    key = ALIASES.get(key, key)
    if key not in TYPES:
        raise KeyError(f"unknown content type '{key}'. Choose from: {', '.join(TYPES)}")
    return TYPES[key]


def build_prompt(ct: ContentType, topic: str, *, notes: str = "", source: str = "",
                 pillar: str | None = None, offer: str | None = None) -> str:
    parts = [f"<task>{ct.brief}</task>", f"<topic>{topic}</topic>"]
    if pillar:
        parts.append(f"<content_pillar>{pillar}</content_pillar>")
    if offer:
        parts.append(f"<promote_offer>{offer}</promote_offer>")
    if source:
        parts.append("<source_material>\nRepurpose this piece. Keep its core ideas and any facts; "
                     f"adapt format and length to the channel.\n{source}\n</source_material>")
    if notes:
        parts.append(f"<notes>{notes}</notes>")
    parts.append("<constraints>\n" + "\n".join(f"- {c}" for c in ct.constraints) + "\n</constraints>")
    return "\n\n".join(parts)


def build_revision_prompt(issues: list[str]) -> str:
    return ("Your draft failed validation:\n" + "\n".join(f"- {i}" for i in issues) +
            "\n\nReturn the full corrected JSON. Fix every issue; keep everything else that worked.")


def review_prompt(draft: str, channel: str | None) -> str:
    return (f"<task>Review this draft{f' for {channel}' if channel else ''} against the brand voice & tone, "
            "word lists, example posts and the ICP (pains, desires, objections, language). Score it, list "
            "strengths and issues, suggest concrete line edits, and provide a revised draft that fixes the "
            "issues without banned words.</task>\n\n"
            f"<draft>\n{draft}\n</draft>")


def calendar_prompt(slots: list[dict]) -> str:
    rows = "\n".join(f"{x['slot']}. {x['date']} | {x['channel']} | pillar: {x['pillar']}" for x in slots)
    return ("<task>Fill this content calendar. For every slot propose one specific topic, an opening hook "
            "and a CTA that fit the channel and the content pillar, avoid repeating topics, and build "
            "toward the brand's offers across the period.</task>\n\n"
            f"<slots>\n{rows}\n</slots>\n\n<constraints>\n- exactly one idea per slot number\n"
            "- hooks <= 120 characters\n</constraints>")
