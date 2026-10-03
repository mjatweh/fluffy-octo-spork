"""Output dataclasses. JSON schemas for structured outputs are derived from the type hints."""
from __future__ import annotations

import dataclasses
import typing
from dataclasses import dataclass, fields, is_dataclass


def d(text: str):
    """Required field with a description that is copied into the JSON schema."""
    return dataclasses.field(metadata={"description": text})


# ------------------------------------------------------------------ social
@dataclass
class LinkedInPost:
    hook: str = d("First 1-2 lines shown before 'see more'; must stop the scroll")
    body: str = d("Main post body: short paragraphs separated by blank lines, plain text, no markdown")
    cta: str = d("Closing call to action or engagement question")
    hashtags: list[str] = d("3-5 relevant hashtags, without the # symbol")


@dataclass
class XPost:
    text: str = d("The complete tweet text, max 280 characters including hashtags")


@dataclass
class XThread:
    tweets: list[str] = d("Tweets in order; tweet 1 is the hook; each max 280 characters")


@dataclass
class CarouselSlide:
    title: str = d("Large on-slide headline")
    body: str = d("Supporting on-slide text, 1-2 short sentences")
    visual: str = d("Design/visual direction for this slide")


@dataclass
class InstagramPost:
    caption: str = d("Caption: hook line first, short paragraphs, ends with a CTA; no hashtags here")
    hashtags: list[str] = d("5-15 hashtags without the # symbol")
    slides: list[CarouselSlide] = d("Carousel slide outline, 3-10 slides; slide 1 is the hook")


@dataclass
class Shot:
    timestamp: str = d("Time range, e.g. 0:00-0:03")
    visual: str = d("What the camera shows / B-roll")
    voiceover: str = d("What is said during this shot")
    on_screen_text: str = d("Text overlay (empty string if none)")


@dataclass
class VideoScript:
    hook: str = d("Spoken hook for the first 1-3 seconds")
    body: list[str] = d("Spoken body beats, in order")
    cta: str = d("Spoken call to action at the end")
    duration_seconds: int = d("Target duration in seconds (15-90)")
    shots: list[Shot] = d("Shot list covering the whole video")


# ------------------------------------------------------------------ email
@dataclass
class NewsletterSection:
    heading: str = d("Section heading")
    body_markdown: str = d("Section body in markdown (paragraphs, bullet lists, **bold**, [links](url))")


@dataclass
class Newsletter:
    subject_lines: list[str] = d("3-5 subject line variants, each max 60 characters")
    preview_text: str = d("Inbox preview text, max 140 characters, complements the subject")
    title: str = d("Headline at the top of the email")
    sections: list[NewsletterSection] = d("2-5 body sections")
    cta_text: str = d("Button text for the main call to action")
    cta_url: str = d("URL for the main call to action")
    sign_off: str = d("Closing line and signature")


# ------------------------------------------------------------------ assets
@dataclass
class Benefit:
    title: str = d("Benefit headline")
    description: str = d("1-2 sentences in customer language")


@dataclass
class FAQ:
    question: str = d("Question as the customer would ask it (often an objection)")
    answer: str = d("Concise, honest answer")


@dataclass
class LandingPage:
    hero_headline: str = d("Hero headline, max 80 characters")
    hero_subheadline: str = d("Hero subheadline, max 200 characters")
    primary_cta: str = d("Primary button text")
    benefits: list[Benefit] = d("3-6 benefits")
    social_proof: list[str] = d("2-4 social proof PLACEHOLDERS in [square brackets], e.g. [Testimonial from ...]; never invent quotes or numbers")
    faq: list[FAQ] = d("4-8 FAQs addressing objections")
    final_cta: str = d("Closing CTA section copy")


@dataclass
class AdVariant:
    angle: str = d("The angle/hypothesis this variant tests")
    headline: str = d("Headline, max 40 characters")
    primary_text: str = d("Primary text, max 125 characters")
    description: str = d("Description, max 30 characters")


@dataclass
class AdCopy:
    variants: list[AdVariant] = d("3-5 distinct ad variants")


@dataclass
class OutlineSection:
    heading: str = d("H2 heading")
    points: list[str] = d("2-5 key points to cover")


@dataclass
class BlogOutline:
    title: str = d("Post title, max 70 characters")
    meta_description: str = d("SEO meta description, max 160 characters")
    target_keyword: str = d("Primary search keyword")
    intro: str = d("2-3 sentence intro angle")
    sections: list[OutlineSection] = d("4-10 sections")
    cta: str = d("Closing call to action")


# ------------------------------------------------------------------ calendar / review
@dataclass
class CalendarIdea:
    slot: int = d("The slot number this idea fills")
    topic: str = d("Specific topic for this piece")
    hook: str = d("Opening hook line")
    cta: str = d("Call to action")


@dataclass
class CalendarPlan:
    ideas: list[CalendarIdea] = d("Exactly one idea per slot")


@dataclass
class SuggestedEdit:
    original: str = d("Exact text from the draft")
    suggestion: str = d("Replacement text")
    reason: str = d("Why, referencing the brand voice or ICP")


@dataclass
class Review:
    overall_score: int = d("0-100 overall fit")
    voice_score: int = d("0-100 match to the brand voice & tone and word lists")
    icp_score: int = d("0-100 relevance to the ICP's pains, desires and language")
    summary: str = d("2-3 sentence verdict")
    strengths: list[str] = d("What works")
    issues: list[str] = d("What doesn't fit")
    suggested_edits: list[SuggestedEdit] = d("Concrete line edits")
    revised_draft: str = d("The full draft rewritten to fix the issues")


# ------------------------------------------------------------------ helpers
_PRIMITIVES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def schema_for(tp) -> dict:
    """JSON schema (structured-outputs compatible) for a dataclass / list / primitive type."""
    if is_dataclass(tp):
        hints = typing.get_type_hints(tp)
        props = {}
        for f in fields(tp):
            s = schema_for(hints[f.name])
            if f.metadata.get("description"):
                s["description"] = f.metadata["description"]
            props[f.name] = s
        return {"type": "object", "properties": props, "required": list(props),
                "additionalProperties": False}
    if typing.get_origin(tp) is list:
        return {"type": "array", "items": schema_for(typing.get_args(tp)[0])}
    return {"type": _PRIMITIVES[tp]}


def from_dict(tp, data):
    """Parse JSON data into dataclass instances, raising ValueError on shape mismatches."""
    if is_dataclass(tp):
        if not isinstance(data, dict):
            raise ValueError(f"expected object for {tp.__name__}, got {type(data).__name__}")
        hints = typing.get_type_hints(tp)
        kwargs = {}
        for f in fields(tp):
            if f.name not in data:
                raise ValueError(f"{tp.__name__}: missing field '{f.name}'")
            kwargs[f.name] = from_dict(hints[f.name], data[f.name])
        return tp(**kwargs)
    if typing.get_origin(tp) is list:
        if not isinstance(data, list):
            raise ValueError(f"expected list, got {type(data).__name__}")
        return [from_dict(typing.get_args(tp)[0], x) for x in data]
    if tp is int:
        return int(data)
    if tp is str:
        return "" if data is None else str(data)
    return data


def iter_strings(obj, path: str = ""):
    """Yield (path, text) for every string inside a dataclass tree."""
    if isinstance(obj, str):
        yield path, obj
    elif is_dataclass(obj):
        for f in fields(obj):
            yield from iter_strings(getattr(obj, f.name), f"{path}.{f.name}" if path else f.name)
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            yield from iter_strings(x, f"{path}[{i}]")
