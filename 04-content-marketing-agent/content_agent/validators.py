"""Format/brand validators. Each returns a list of human-readable issues (empty == valid)."""
from __future__ import annotations

import re

from . import schemas as s

X_LIMIT = 280
_URL = re.compile(r"https?://\S+")


def x_length(text: str) -> int:
    """Approximate X weighted length: every URL counts as 23 characters."""
    return len(_URL.sub("x" * 23, text))


def banned_pattern(word: str) -> re.Pattern:
    """Whole-word, case-insensitive match that also catches simple inflections (s/es/d/ed/ing)."""
    return re.compile(rf"(?<![\w-]){re.escape(word)}(?:s|es|d|ed|ing)?(?![\w-])", re.I)


def find_banned(obj, banned: list[str]) -> list[str]:
    issues = []
    for word in banned:
        pat = banned_pattern(word)
        for path, text in s.iter_strings(obj):
            if pat.search(text):
                issues.append(f"banned word '{word}' used in {path}")
    return issues


def _max(issues, label, text, limit, measure=len):
    if measure(text) > limit:
        issues.append(f"{label} is {measure(text)} chars (max {limit})")


def _count(issues, label, items, lo, hi):
    if not lo <= len(items) <= hi:
        issues.append(f"{label}: {len(items)} items (need {lo}-{hi})")


def _empty(issues, obj):
    for path, text in s.iter_strings(obj):
        if not text.strip() and not path.endswith("on_screen_text"):
            issues.append(f"{path} is empty")


def v_linkedin(p: s.LinkedInPost, issues):
    _max(issues, "hook", p.hook, 210)
    total = "\n\n".join([p.hook, p.body, p.cta, " ".join("#" + h for h in p.hashtags)])
    _max(issues, "post", total, 3000)
    _count(issues, "hashtags", p.hashtags, 3, 5)


def v_x(p: s.XPost, issues):
    _max(issues, "tweet", p.text, X_LIMIT, x_length)
    if p.text.count("#") > 2:
        issues.append("tweet: use at most 2 hashtags")


def v_x_thread(p: s.XThread, issues):
    _count(issues, "tweets", p.tweets, 3, 12)
    for i, t in enumerate(p.tweets, 1):
        _max(issues, f"tweet {i}", t, X_LIMIT, x_length)


def v_instagram(p: s.InstagramPost, issues):
    _max(issues, "caption", p.caption + "\n\n" + " ".join("#" + h for h in p.hashtags), 2200)
    _count(issues, "hashtags", p.hashtags, 5, 15)
    _count(issues, "carousel slides", p.slides, 3, 10)
    for i, sl in enumerate(p.slides, 1):
        _max(issues, f"slide {i} title", sl.title, 60)


def v_tiktok(p: s.VideoScript, issues):
    _max(issues, "hook", p.hook, 120)
    if not 15 <= p.duration_seconds <= 90:
        issues.append(f"duration_seconds {p.duration_seconds} (need 15-90)")
    words = len(" ".join([p.hook, *p.body, p.cta]).split())
    if words > p.duration_seconds * 3:
        issues.append(f"script has {words} spoken words; too long for {p.duration_seconds}s (max ~{p.duration_seconds * 3})")
    _count(issues, "shots", p.shots, 3, 20)
    _count(issues, "body beats", p.body, 1, 10)


def v_newsletter(p: s.Newsletter, issues):
    _count(issues, "subject_lines", p.subject_lines, 3, 5)
    for i, sl in enumerate(p.subject_lines, 1):
        _max(issues, f"subject line {i}", sl, 60)
    _max(issues, "preview_text", p.preview_text, 140)
    _count(issues, "sections", p.sections, 2, 5)


def v_landing_page(p: s.LandingPage, issues):
    _max(issues, "hero_headline", p.hero_headline, 80)
    _max(issues, "hero_subheadline", p.hero_subheadline, 200)
    _max(issues, "primary_cta", p.primary_cta, 40)
    _count(issues, "benefits", p.benefits, 3, 6)
    _count(issues, "faq", p.faq, 4, 8)
    _count(issues, "social_proof", p.social_proof, 2, 4)
    for i, sp in enumerate(p.social_proof, 1):
        if "[" not in sp or "]" not in sp:
            issues.append(f"social_proof {i} must be a [placeholder], not an invented testimonial")


def v_ads(p: s.AdCopy, issues):
    _count(issues, "variants", p.variants, 3, 5)
    for i, v in enumerate(p.variants, 1):
        _max(issues, f"variant {i} headline", v.headline, 40)
        _max(issues, f"variant {i} primary_text", v.primary_text, 125)
        _max(issues, f"variant {i} description", v.description, 30)


def v_blog_outline(p: s.BlogOutline, issues):
    _max(issues, "title", p.title, 70)
    _max(issues, "meta_description", p.meta_description, 160)
    _count(issues, "sections", p.sections, 4, 10)
    for i, sec in enumerate(p.sections, 1):
        _count(issues, f"section {i} points", sec.points, 2, 5)


def v_review(p: s.Review, issues):
    for name in ("overall_score", "voice_score", "icp_score"):
        if not 0 <= getattr(p, name) <= 100:
            issues.append(f"{name} must be 0-100")


VALIDATORS = {
    s.LinkedInPost: v_linkedin, s.XPost: v_x, s.XThread: v_x_thread, s.InstagramPost: v_instagram,
    s.VideoScript: v_tiktok, s.Newsletter: v_newsletter, s.LandingPage: v_landing_page,
    s.AdCopy: v_ads, s.BlogOutline: v_blog_outline, s.Review: v_review,
}


def validate(obj, banned: list[str] | None = None) -> list[str]:
    issues: list[str] = []
    if not isinstance(obj, s.Review):  # reviews quote the draft, so they may contain banned words
        _empty(issues, obj)
        issues += find_banned(obj, banned or [])
    fn = VALIDATORS.get(type(obj))
    if fn:
        fn(obj, issues)
    return issues


def _trim(text: str, limit: int, measure=len) -> str:
    if measure(text) <= limit:
        return text
    words = text.split(" ")
    while words and measure(" ".join(words) + "…") > limit:
        words.pop()
    return (" ".join(words) or text[: limit - 1]).rstrip(" ,;:") + "…"


def enforce(obj):
    """Last-resort hard enforcement of character/count limits after revisions are exhausted."""
    if isinstance(obj, s.XPost):
        obj.text = _trim(obj.text, X_LIMIT, x_length)
    elif isinstance(obj, s.XThread):
        obj.tweets = [_trim(t, X_LIMIT, x_length) for t in obj.tweets[:12]]
    elif isinstance(obj, s.LinkedInPost):
        obj.hashtags = obj.hashtags[:5]
    elif isinstance(obj, s.InstagramPost):
        obj.hashtags, obj.slides = obj.hashtags[:15], obj.slides[:10]
    elif isinstance(obj, s.Newsletter):
        obj.subject_lines = [_trim(x, 60) for x in obj.subject_lines[:5]]
        obj.preview_text = _trim(obj.preview_text, 140)
    elif isinstance(obj, s.AdCopy):
        for v in obj.variants:
            v.headline, v.primary_text, v.description = (
                _trim(v.headline, 40), _trim(v.primary_text, 125), _trim(v.description, 30))
    elif isinstance(obj, s.BlogOutline):
        obj.meta_description = _trim(obj.meta_description, 160)
    return obj


def normalize(obj):
    """Cosmetic cleanup before validation (hashtags without '#', stripped whitespace)."""
    for name in ("hashtags",):
        if hasattr(obj, name):
            setattr(obj, name, [h.strip().lstrip("#").replace(" ", "") for h in getattr(obj, name) if h.strip()])
    return obj
