"""Deterministic, offline templated output for --dry-run (no API key needed).

Drafts are assembled from the brand files so they are on-topic and on-brand enough to sanity-check the
pipeline, and they are built to pass the same validators as real model output.
"""
from __future__ import annotations

import hashlib
import re

from . import schemas as s
from .brand import Brand
from .validators import X_LIMIT, _trim, banned_pattern, x_length

_URL = re.compile(r"(https?://[^\s)]+|\b[\w-]+\.(?:ai|com|io|co|org|net)(?:/[^\s)]*)?)")


_STOP = {"your", "with", "that", "this", "from", "what", "when", "why", "how", "have", "into", "about"}


def key_sentences(source: str, n: int = 4) -> list[str]:
    """Pick the most concrete sentences (numbers, lessons, actions) from a long piece, in original order."""
    body = "\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", re.sub(r"[*>`_]", "", body)) if len(x.split()) > 4]
    score = lambda x: bool(re.search(r"\d", x)) + bool(re.search(r"lesson|start|measure|built|automat|result|instead", x, re.I))  # noqa: E731
    top = sorted(range(len(sents)), key=lambda i: (-score(sents[i]), i))[:n]
    return [sents[i] for i in sorted(top)]


class Material:
    """Brand facts picked deterministically per topic."""

    def __init__(self, brand: Brand, topic: str, source: str = "", offer: str | None = None,
                 pillar: str | None = None):
        seed = int(hashlib.sha256(topic.encode()).hexdigest(), 16)
        pick = lambda xs, fb, k=0: xs[(seed + k) % len(xs)] if xs else fb  # noqa: E731
        self.topic = topic.strip().rstrip(".")
        self.name = brand.name
        self.pain = pick(brand.pains, "too much busywork").rstrip(".").replace('"', "'")
        self.pain2 = pick(brand.pains, "no time", 1).rstrip(".")
        self.desire = pick(brand.desires, "more time for what matters").rstrip(".")
        self.objection = pick(brand.objections, "it sounds expensive").rstrip(".")
        self.phrase = pick(brand.language, "where do I even start").strip("\"'“”")
        offers = brand.offers
        self.offer = offer if offer in offers else (next(iter(offers)) if offers else "our offer")
        offer_text = offers.get(self.offer, "")
        self.offer_line = (re.split(r"(?<=[.!?])\s", offer_text.strip())[0] if offer_text else "")
        url = _URL.search(offer_text) or _URL.search(" ".join(offers.values()))
        self.url = url.group(1).rstrip(".") if url else "https://example.com"
        if not self.url.startswith("http"):
            self.url = "https://" + self.url
        self.pillar = pillar or (brand.pillars[seed % len(brand.pillars)].name if brand.pillars else "Insights")
        self.points = key_sentences(source) or [
            "Start with the real problem, not the tool.",
            "Pick one workflow and measure it before you change anything.",
            "Fix the process first, then add tools.",
            "Measure the result so the win is obvious to your team.",
        ]

    @property
    def hashtags(self) -> list[str]:
        words = [w[0].upper() + w[1:] for w in re.findall(r"[A-Za-z]+", self.topic)
                 if len(w) > 3 and w.lower() not in _STOP][:3]
        tags = ["".join(words)] if words else []
        tags += [re.sub(r"\W", "", self.pillar.title())[:30], re.sub(r"\W", "", self.name), "SmallBusiness",
                 "Productivity", "Operations", "Marketing", "Founders", "Growth", "Strategy"]
        return [t for i, t in enumerate(tags) if t and t not in tags[:i]]


def linkedin(m: Material) -> s.LinkedInPost:
    body = (f"\"{m.pain}.\"\n\nI hear some version of this every week. Here's what I'd tell you:\n\n" + "\n".join(f"→ {p}" for p in m.points[:4]) +
            f"\n\nThe goal isn't more tools. The goal: {m.desire.lower()}.")
    return s.LinkedInPost(hook=_trim(f"{m.topic}: most people start in the wrong place.", 210),
                          body=body, cta=f"Want help with this? {m.offer}: {m.url}", hashtags=m.hashtags[:4])


def x(m: Material) -> s.XPost:
    text = f"{m.topic}: {m.points[0]} {m.points[1]} #{m.hashtags[0]}"
    if x_length(text) > X_LIMIT:
        text = _trim(f"{m.topic}: {m.points[0]}", X_LIMIT - len(m.hashtags[0]) - 2, x_length) + f" #{m.hashtags[0]}"
    return s.XPost(text=text)


def x_thread(m: Material) -> s.XThread:
    tweets = [f"{m.topic} — a short thread. 🧵", f"The problem: \"{m.pain}.\" Sound familiar?"]
    tweets += [p for p in m.points[:4]]
    tweets.append(f"If you want a hand: {m.offer} → {m.url}")
    return s.XThread(tweets=[_trim(f"{i}/ {t}", X_LIMIT, x_length) for i, t in enumerate(tweets, 1)])


def instagram(m: Material) -> s.InstagramPost:
    caption = (f"{m.topic} 👇\n\n\"{m.pain}.\" If that's you, save this.\n\n" +
               "\n".join(f"• {p}" for p in m.points[:4]) + f"\n\nWant help? {m.offer} — link in bio.")
    slides = [s.CarouselSlide(_trim(m.topic, 60), "Swipe for the short version →", "Bold title on brand color")]
    slides += [s.CarouselSlide(f"Step {i}", _trim(p, 140), "Simple icon + one line of text")
               for i, p in enumerate(m.points[:4], 1)]
    slides.append(s.CarouselSlide("Want help?", f"{m.offer}. Link in bio.", "Logo, CTA button graphic"))
    return s.InstagramPost(caption=caption, hashtags=m.hashtags[:10], slides=slides)


def tiktok(m: Material) -> s.VideoScript:
    hook = _trim(f"Stop. If you've ever said \"{m.phrase}\", watch this.", 120)
    body = [_trim(p, 160) for p in m.points[:3]]
    cta = f"Follow for more, or check out {m.offer} at the link in bio."
    words = len(" ".join([hook, *body, cta]).split())
    duration = min(90, max(20, -(-words // 25) * 10))
    times = [0, 3] + [3 + (duration - 3) * (i + 1) // len(body) for i in range(len(body))]
    ts = lambda a, b: f"0:{a:02d}-0:{b:02d}" if b < 60 else f"{a // 60}:{a % 60:02d}-{b // 60}:{b % 60:02d}"  # noqa: E731
    shots = [s.Shot(ts(times[0], times[1]), "Face to camera, close-up", hook, _trim(m.topic, 40))]
    shots += [s.Shot(ts(times[i + 1], times[i + 2]), "B-roll / screen recording illustrating the point",
                     b, f"Tip {i + 1}") for i, b in enumerate(body)]
    shots[-1] = s.Shot(shots[-1].timestamp, shots[-1].visual, shots[-1].voiceover + " " + cta, "Link in bio")
    return s.VideoScript(hook=hook, body=body, cta=cta, duration_seconds=duration, shots=shots)


def newsletter(m: Material) -> s.Newsletter:
    subjects = [_trim(m.topic, 60), _trim(f"\"{m.phrase}\"? Start here", 60),
                _trim(f"{m.topic}: the short version", 60), "One small change, big payoff"]
    sections = [
        s.NewsletterSection("The problem", f"Most of the people we talk to say some version of: *\"{m.pain}.\"*\n\n"
                                           f"If that's you, this issue is for you: **{m.topic}**."),
        s.NewsletterSection("What to do this week", "\n".join(f"- {p}" for p in m.points[:4])),
        s.NewsletterSection("The objection we always hear", f"\"{m.objection}.\" Fair. Start small, measure it, "
                                                            f"and let the result make the case."),
    ]
    return s.Newsletter(subject_lines=subjects, preview_text=_trim(f"What you actually want: {m.desire.lower()}. Here's a practical first step.", 140),
                        title=m.topic, sections=sections, cta_text=_trim(m.offer, 40), cta_url=m.url,
                        sign_off=f"Talk soon,\nThe {m.name} team")


def landing_page(m: Material) -> s.LandingPage:
    benefits = [s.Benefit(_trim(p.rstrip("."), 60), p) for p in m.points[:3]]
    benefits.append(s.Benefit(_trim(m.desire, 60), f"Built around one outcome: {m.desire.lower()}."))
    faq = [s.FAQ(f"\"{m.objection}?\"", "[Answer this objection honestly, with your process and guarantees.]"),
           s.FAQ("Who is this for?", "[Describe your ideal customer in one sentence.]"),
           s.FAQ("How long does it take?", "[Timeline from offers.md.]"),
           s.FAQ("What does it cost?", f"See {m.offer} details: {m.url}")]
    return s.LandingPage(
        hero_headline=_trim(m.topic, 80),
        hero_subheadline=_trim(m.offer_line or f"{m.name} helps you {m.desire.lower()}.", 200),
        primary_cta=_trim(f"Get started with {m.offer}", 40), benefits=benefits,
        social_proof=["[Testimonial from a client in your ICP, with name and role]",
                      "[Result metric: hours/money saved, with source]", "[Client logos]"],
        faq=faq, final_cta=f"{m.desire}? Start with {m.offer}: {m.url}")


def ads(m: Material) -> s.AdCopy:
    angles = [("Pain", f"\"{m.pain}\"?", f"{m.pain}. There's a simpler way: {m.offer}."),
              ("Desire", m.desire, f"{m.desire}. {m.offer} shows you how."),
              ("Objection", m.objection, f"\"{m.objection}.\" We hear you. Start small with {m.offer}.")]
    return s.AdCopy(variants=[s.AdVariant(a, _trim(h, 40), _trim(t, 125), _trim(m.offer, 30)) for a, h, t in angles])


def blog_outline(m: Material) -> s.BlogOutline:
    secs = [s.OutlineSection("Why this matters now", [f"The pain: {m.pain.lower()}", f"What it costs you"]),
            *[s.OutlineSection(_trim(p.rstrip("."), 70), ["Explain the idea", "Give a concrete example"])
              for p in m.points[:3]],
            s.OutlineSection(f"\"{m.objection}\" — answered", ["Name the objection", "Answer it honestly"]),
            s.OutlineSection("Your next step", ["Recap", f"Point to {m.offer}"])]
    return s.BlogOutline(title=_trim(m.topic, 70),
                         meta_description=_trim(f"{m.topic}: a practical, no-hype guide with steps you can use this week.", 160),
                         target_keyword=m.topic.lower(), intro=f"Open with the reader's words: \"{m.phrase}\".",
                         sections=secs, cta=f"{m.offer}: {m.url}")


BUILDERS = {"linkedin": linkedin, "x": x, "x-thread": x_thread, "instagram": instagram, "tiktok": tiktok,
            "newsletter": newsletter, "landing-page": landing_page, "ads": ads, "blog-outline": blog_outline}


def build(key: str, brand: Brand, topic: str, *, source: str = "", offer: str | None = None,
          pillar: str | None = None):
    return BUILDERS[key](Material(brand, topic, source=source, offer=offer, pillar=pillar))


_HOOKS = ("\"{pain}.\" Here's the fix.", "{topic} — the honest version.",
          "If you've ever said \"{phrase}\", this one's for you.", "Nobody talks about this part: {topic_l}.")


def calendar_ideas(brand: Brand, slots: list[dict]) -> s.CalendarPlan:
    by_pillar = {p.name: p.topics or [p.name] for p in brand.pillars}
    offers = list(brand.offers) or ["our offer"]
    used: dict[str, int] = {}
    ideas = []
    for sl in slots:
        topics = by_pillar.get(sl["pillar"], [sl["pillar"]])
        i = used.get(sl["pillar"], 0)
        used[sl["pillar"]] = i + 1
        topic = topics[i % len(topics)]
        m = Material(brand, topic, offer=offers[sl["slot"] % len(offers)])
        hook = _HOOKS[sl["slot"] % len(_HOOKS)].format(pain=m.pain.replace('"', "'"), phrase=m.phrase, topic=topic,
                                                       topic_l=topic[0].lower() + topic[1:])
        ideas.append(s.CalendarIdea(sl["slot"], topic, _trim(hook, 120), f"{m.offer}: {m.url}"))
    return s.CalendarPlan(ideas=ideas)


_COMMON = {"about", "going", "their", "there", "where", "which", "without", "instead", "every", "start",
           "people", "things", "really", "think", "would", "could", "should", "being", "these", "those"}


def review(brand: Brand, draft: str) -> s.Review:
    """Heuristic scoring: banned/preferred words, ICP language & pains, readability."""
    low = draft.lower()
    banned = [w for w in brand.banned_words if banned_pattern(w).search(low)]
    used = [w for w in brand.do_words if w.lower() in low]
    icp_terms = {t for t in re.findall(r"[a-z]{6,}", " ".join(brand.pains + brand.desires + brand.language).lower())} - _COMMON
    hits = {t for t in icp_terms if t in low}
    sentences = [x for x in re.split(r"[.!?]+\s", draft) if x.strip()]
    avg = sum(len(x.split()) for x in sentences) / max(1, len(sentences))
    you = len(re.findall(r"\byou(r)?\b", low))
    voice = max(0, min(100, 70 + 6 * len(used) - 20 * len(banned) - (10 if avg > 22 else 0)))
    icp = max(0, min(100, 40 + 6 * len(hits) + (10 if you else 0)))
    strengths, issues, edits = [], [], []
    if used:
        strengths.append("Uses on-brand language: " + ", ".join(used))
    if hits:
        strengths.append("Speaks to ICP themes: " + ", ".join(sorted(hits)[:6]))
    if avg <= 18:
        strengths.append(f"Short, readable sentences (avg {avg:.0f} words)")
    alt = {w: (re.search(r'say "([^"]+)"', r) or [None, None])[1] for w, r in brand.banned_map.items()}
    for w in banned:
        reason = brand.banned_map.get(w)
        issues.append(f"Uses banned word '{w}'" + (f" ({reason})" if reason else ""))
    for sent in re.findall(r"[^.!?\n]+[.!?]?", draft):
        hit = [w for w in banned if banned_pattern(w).search(sent)]
        if hit:
            fixed = sent
            for w in hit:
                fixed = banned_pattern(w).sub(alt.get(w) or "[…]", fixed)
            edits.append(s.SuggestedEdit(sent.strip(), fixed.strip(), "Avoid: " + ", ".join(hit)))
    if avg > 22:
        issues.append(f"Long sentences (avg {avg:.0f} words); the voice favors short ones")
    if not you:
        issues.append("Doesn't address the reader directly ('you')")
    if len(hits) < 2:
        issues.append("Weak connection to the ICP's pains/desires; use their language: " + ", ".join(brand.language[:3]))
    revised = draft
    for e in edits:
        revised = revised.replace(e.original, e.suggestion)
    return s.Review(overall_score=round((voice + icp) / 2), voice_score=voice, icp_score=icp,
                    summary=f"Heuristic (dry-run) review: voice {voice}/100, ICP fit {icp}/100. "
                            f"{len(issues)} issue(s) found.",
                    strengths=strengths, issues=issues, suggested_edits=edits, revised_draft=revised)
