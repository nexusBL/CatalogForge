"""Reject untrusted model output. Never rewrite hallucinated text into an accepted proposal."""

from __future__ import annotations

import re
from typing import Any

from backend.improvement.contract import (
    MAX_CATEGORY_NAME_CHARS,
    MAX_DESCRIPTION_CHARS,
    MAX_LABEL_CHARS,
    MAX_LABELS,
    GeneratorCandidate,
    TrustedItemContext,
)

_PRICE_RE = re.compile(
    r"(?:₹|rs\.?|inr|usd|\$)\s*\d|\d+\s*(?:₹|rs\.?|inr)|mrp\b|\brs\b\s*\d",
    re.IGNORECASE,
)
_QTY_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|g|kg|ml|l|kcal|cal|grams?|kilograms?|litres?|liters?|pieces?|pcs)\b",
    re.IGNORECASE,
)
_INJECTION_RE = re.compile(
    r"\b(ignore (?:all |any )?previous|system prompt|you are now|drop table|insert into|alter table)\b",
    re.IGNORECASE,
)
_META_PHRASES_RE = re.compile(
    r"\b(from (?:our|the) menu|listed under|menu section|this menu|our menu|drinks menu|food menu)\b",
    re.IGNORECASE,
)

CLAIM_PHRASES = (
    "gluten-free",
    "gluten free",
    "dairy-free",
    "dairy free",
    "nut-free",
    "nut free",
    "allergen",
    "contains nuts",
    "contains milk",
    "certified",
    "organic certified",
    "fssai certified",
    "award",
    "awarded",
    "michelin",
    "bestseller of the year",
    "iso ",
    "halal certified",
    "kosher",
    "100% vegetarian certified",
    "no msg",
    "msg-free",
    "sugar-free",
    "sugar free",
    "keto",
    "vegan",
    "jain",
    "available 24",
    "sold out",
    "out of stock",
    "always available",
    "freshly prepared",
    "deep fried",
    "deep-fried",
    "shallow fried",
    "tandoor",
    "slow cooked",
    "slow-cooked",
    "marinated overnight",
    "homemade",
    "home-made",
    "secret recipe",
    "chef's special spice",
    "imported",
    "export quality",
)

INGREDIENT_TOKENS = frozenset(
    {
        "potato",
        "potatoes",
        "tomato",
        "tomatoes",
        "onion",
        "onions",
        "garlic",
        "ginger",
        "chicken",
        "mutton",
        "lamb",
        "beef",
        "pork",
        "fish",
        "prawn",
        "prawns",
        "shrimp",
        "egg",
        "eggs",
        "paneer",
        "cheese",
        "cream",
        "butter",
        "ghee",
        "yogurt",
        "yoghurt",
        "curd",
        "milk",
        "cashew",
        "cashews",
        "almond",
        "almonds",
        "peanut",
        "peanuts",
        "coconut",
        "sambar",
        "chutney",
        "rasam",
        "dal",
        "dhal",
        "lentil",
        "lentils",
        "chickpea",
        "chickpeas",
        "chana",
        "rajma",
        "mushroom",
        "mushrooms",
        "spinach",
        "palak",
        "capsicum",
        "pepper",
        "chili",
        "chilli",
        "chillies",
        "coriander",
        "cumin",
        "turmeric",
        "saffron",
        "basmati",
        "rice",
        "wheat",
        "maida",
        "atta",
        "flour",
        "oil",
        "olive",
        "mustard",
        "pickle",
        "papad",
        "chips",
        "chip",
        "dip",
        "nachos",
        "salsa",
        "mayonnaise",
        "mayo",
        "ketchup",
        "chocolate",
        "vanilla",
        "strawberry",
        "mango",
        "banana",
        "apple",
        "orange",
        "lemon",
        "lime",
        "mint",
        "coffee",
        "tea",
        "sugar",
        "honey",
        "jaggery",
        "salt",
        "masala",
        "gravy",
        "curry",
        "biryani",
        "naan",
        "roti",
        "idli",
        "dosa",
        "vada",
        "uttapam",
        "upma",
        "poha",
        "puri",
        "poori",
        "paratha",
        "kulcha",
        "pizza",
        "pasta",
        "noodle",
        "noodles",
        "burger",
        "sandwich",
        "wrap",
        "taco",
        "bacon",
        "ham",
        "sausage",
        "truffle",
        "caviar",
        "foie",
    }
)


class CandidateRejected(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _tokens(text: str) -> set[str]:
    return {part.casefold() for part in re.findall(r"[A-Za-z][A-Za-z']+", text)}


def _is_trusted_ingredient_token(token: str, trusted_tokens: set[str]) -> bool:
    if token in trusted_tokens:
        return True
    if token in {"noodle", "noodles"} and "maggi" in trusted_tokens:
        return True
    for t in trusted_tokens:
        if len(t) >= 4 and len(token) >= 4:
            if t.startswith(token) or token.startswith(t):
                return True
    return False


def trusted_blob(context: TrustedItemContext) -> str:
    parts = [
        context.name or "",
        context.category_name or "",
        context.current_value or "",
        context.food_type or "",
        " ".join(context.labels),
        f"₹{context.original_price}" if context.original_price else "",
    ]
    if context.kind != "description":
        parts.append(context.restaurant_name or "")
    elif context.restaurant_name and (
        context.restaurant_name.casefold() in (context.name or "").casefold()
        or context.restaurant_name.casefold() in (context.current_value or "").casefold()
    ):
        parts.append(context.restaurant_name)
    if context.current_proposal_value:
        parts.append(context.current_proposal_value)
    return " ".join(parts)


def validate_candidate(context: TrustedItemContext, candidate: GeneratorCandidate) -> str:
    raw = candidate.proposed_value
    if raw is None:
        raise CandidateRejected("empty output")
    text = str(raw).strip()
    if not text:
        raise CandidateRejected("empty output")
    if context.kind == "description":
        limit = MAX_DESCRIPTION_CHARS
    else:
        limit = MAX_CATEGORY_NAME_CHARS
    if len(text) > limit:
        raise CandidateRejected("excessive output")
    if "\x00" in text:
        raise CandidateRejected("malformed output")
    if _INJECTION_RE.search(text):
        raise CandidateRejected("unsupported claims")
    if _PRICE_RE.search(text):
        raise CandidateRejected("unsupported claims")
    if _QTY_RE.search(text):
        raise CandidateRejected("unsupported claims")
    blob = trusted_blob(context)
    blob_cf = blob.casefold()
    text_cf = text.casefold()
    for phrase in CLAIM_PHRASES:
        if phrase in text_cf and phrase not in blob_cf:
            raise CandidateRejected("unsupported claims")
    proposed_tokens = _tokens(text)
    trusted_tokens = _tokens(blob)
    invented = {
        token
        for token in (proposed_tokens & INGREDIENT_TOKENS)
        if not _is_trusted_ingredient_token(token, trusted_tokens)
    }
    if invented:
        raise CandidateRejected("hallucinated ingredients")
    name_tokens = {token for token in _tokens(context.name) if len(token) > 2}
    if context.kind == "description" and name_tokens and proposed_tokens.isdisjoint(name_tokens):
        # Proposed copy must remain identifiable as this item.
        raise CandidateRejected("unsupported claims")
    name_clean = context.name.strip().casefold()
    if context.kind == "description" and name_clean:
        if text_cf == name_clean:
            raise CandidateRejected("empty output")
        if _META_PHRASES_RE.search(text_cf):
            raise CandidateRejected("unsupported claims")
        if (
            context.restaurant_name
            and context.restaurant_name.casefold() not in (context.name or "").casefold()
            and context.restaurant_name.casefold() in text_cf
        ):
            raise CandidateRejected("unsupported claims")
        # Reject trivial title-only variants wrapped in punctuation or generic boilerplate
        stripped_text = re.sub(r"^(?:a|an|the|our|classic|fresh|signature)\s+", "", text_cf)
        stripped_text = re.sub(r"[\s\.\,\!\-\:\;]+$", "", stripped_text).strip()
        if (
            stripped_text == name_clean
            or stripped_text == f"{name_clean} dish"
            or stripped_text == f"{name_clean} item"
            or stripped_text == f"{name_clean} option"
            or stripped_text == f"{name_clean} preparation"
        ):
            raise CandidateRejected("empty output")
    return text


def validate_labels(context: TrustedItemContext, labels: list[str]) -> list[str]:
    if not isinstance(labels, list) or not labels:
        raise CandidateRejected("empty output")
    if len(labels) > MAX_LABELS:
        raise CandidateRejected("excessive output")
    cleaned: list[str] = []
    seen: set[str] = set()
    blob = trusted_blob(context)
    blob_cf = blob.casefold()
    trusted_tokens = _tokens(blob)
    for raw in labels:
        if not isinstance(raw, str):
            raise CandidateRejected("malformed JSON")
        text = raw.strip()
        if not text or len(text) > MAX_LABEL_CHARS:
            raise CandidateRejected("malformed output" if not text else "excessive output")
        if "\x00" in text:
            raise CandidateRejected("malformed output")
        if _INJECTION_RE.search(text) or _PRICE_RE.search(text) or _QTY_RE.search(text):
            raise CandidateRejected("unsupported claims")
        text_cf = text.casefold()
        for phrase in CLAIM_PHRASES:
            if phrase in text_cf and phrase not in blob_cf:
                raise CandidateRejected("unsupported claims")
        invented = {
            token
            for token in (_tokens(text) & INGREDIENT_TOKENS)
            if not _is_trusted_ingredient_token(token, trusted_tokens)
        }
        if invented:
            raise CandidateRejected("hallucinated ingredients")
        if text_cf in seen:
            continue
        seen.add(text_cf)
        cleaned.append(text)
    existing = [label.strip() for label in context.labels if label.strip()]
    existing_cf = {label.casefold() for label in existing}
    cleaned_cf = {label.casefold() for label in cleaned}
    if not existing_cf.issubset(cleaned_cf):
        raise CandidateRejected("unsupported claims")
    food = (context.food_type or "").strip()
    if food and food.casefold() not in cleaned_cf:
        raise CandidateRejected("canonical food_type missing")
    if not cleaned:
        raise CandidateRejected("empty output")
    return cleaned


def parse_structured_candidate(payload: Any, *, kind: str = "description") -> GeneratorCandidate:
    if not isinstance(payload, dict):
        raise CandidateRejected("malformed JSON")
    if kind == "labels":
        extra = set(payload.keys()) - {"proposed_labels"}
        if extra:
            raise CandidateRejected("malformed JSON")
        value = payload.get("proposed_labels")
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise CandidateRejected("malformed JSON")
        return GeneratorCandidate(proposed_labels=value, proposed_value="")
    extra = set(payload.keys()) - {"proposed_value"}
    if extra:
        raise CandidateRejected("malformed JSON")
    value = payload.get("proposed_value")
    if not isinstance(value, str):
        raise CandidateRejected("malformed JSON")
    return GeneratorCandidate(proposed_value=value)
