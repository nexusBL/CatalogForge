"""Deterministic owner-mutation parsing. Names only. Forbidden writes stay refused."""

from __future__ import annotations

import re

from backend.catalogue_normalize import coerce_price
from backend.mutation.contract import MutationDraft

_COLLAPSE = re.compile(r"\s+")
_QUOTED = re.compile(r"[\"“”']([^\"“”']+)[\"“”']")
_PRICE = re.compile(
    r"(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)"
    r"|(\d+(?:\.\d+)?)\s*(?:₹|rs\.?|inr|rupees?)"
    r"|\b(?:to|for|at)\s+(\d+(?:\.\d+)?)\b"
    r"|(\d+(?:\.\d+)?)\s*(?:rupees?)?\s*\.?$",
    re.IGNORECASE,
)
_LABEL_SPLIT = re.compile(r"\s*,\s*|\s+and\s+", re.IGNORECASE)

_CONFIRM = frozenset({"yes", "y", "confirm", "confirm change", "confirm the change", "do it", "apply", "ok", "okay"})
_CANCEL = frozenset({"no", "n", "cancel", "never mind", "nevermind", "stop"})


def normalize_message(message: str) -> str:
    return _COLLAPSE.sub(" ", (message or "").strip()).casefold()


def is_confirm_message(message: str) -> bool:
    return normalize_message(message) in _CONFIRM


def is_cancel_message(message: str) -> bool:
    text = normalize_message(message)
    return text in _CANCEL or text.startswith("cancel ")


def parse_mutation_draft(message: str) -> MutationDraft | None:
    raw = _COLLAPSE.sub(" ", (message or "").strip())
    text = raw.casefold()
    if not text:
        return None
    quoted = [match.group(1).strip() for match in _QUOTED.finditer(raw) if match.group(1).strip()]

    if _looks_video(text):
        return MutationDraft(operation="generate_video", item_name=_item_after(raw, ("for", "of")))
    if _looks_image(text):
        return MutationDraft(operation="improve_image", item_name=_item_after(raw, ("for", "of")))
    if _looks_labels(text):
        item, labels = _parse_labels(raw)
        return MutationDraft(operation="update_labels", item_name=item, labels=labels)
    if _looks_description(text):
        return MutationDraft(
            operation="update_description",
            item_name=_item_after(raw, ("for", "of")),
            description=quoted[0] if quoted else None,
        )
    if _looks_rename(text):
        old_name, new_name = _parse_rename(raw, quoted)
        return MutationDraft(operation="rename_item", item_name=old_name, new_item_name=new_name)
    if _looks_move(text):
        item, source, target = _parse_move(raw)
        return MutationDraft(
            operation="move_item",
            item_name=item,
            source_category_name=source,
            target_category_name=target,
        )
    if _looks_add(text):
        name, category, price = _parse_add(raw)
        return MutationDraft(operation="add_item", item_name=name, category_name=category, price=price)
    if _looks_remove(text):
        item, category = _parse_remove(raw)
        return MutationDraft(operation="remove_item", item_name=item, category_name=category)
    if _looks_price(text):
        item, price = _parse_price(raw)
        return MutationDraft(operation="change_price", item_name=item, price=price)
    return None


def _looks_video(text: str) -> bool:
    return bool(re.search(r"\b(generate|create|make)\b", text) and re.search(r"\bvideos?\b", text) and re.search(r"\b(for|of)\b", text))


def _looks_image(text: str) -> bool:
    if not re.search(r"\b(image|photo|picture)s?\b", text):
        return False
    if not re.search(r"\b(for|of)\b", text):
        return False
    return bool(re.search(r"\b(improve|fix|generate|create|enhance)\b", text))


def _looks_labels(text: str) -> bool:
    return bool(re.search(r"\b(tags?|labels)\b", text) and re.search(r"\b(fix|set|update|change)\b", text))


def _looks_description(text: str) -> bool:
    if re.search(r"\bdescriptions\b", text) and not re.search(r"\bdescription (for|of)\b", text):
        return False
    return "description" in text and bool(re.search(r"\b(rewrite|update|set|change|improve|fix)\b", text))


def _looks_rename(text: str) -> bool:
    return text.startswith("rename ") or bool(re.search(r"\bchange the name of\b", text))


def _looks_move(text: str) -> bool:
    return bool(re.match(r"move\s+\S+", text) and re.search(r"\bto\b", text))


def _looks_add(text: str) -> bool:
    if re.search(r"\b(improvement|proposal)\b", text):
        return False
    return bool(re.match(r"add\s+\S+", text))


def _looks_remove(text: str) -> bool:
    if re.search(r"\bcatalogue\b", text):
        return False
    return bool(re.match(r"(remove|delete)\s+\S+", text))


def _looks_price(text: str) -> bool:
    if not _PRICE.search(text):
        return False
    return bool(re.search(r"\b(price|₹|rs|inr|rupees?|change|set|update|make|increase|raise|reduce)\b", text))


def _item_after(raw: str, prepositions: tuple[str, ...]) -> str | None:
    lowered = raw.casefold()
    for word in prepositions:
        token = f" {word} "
        idx = lowered.rfind(token)
        if idx < 0:
            continue
        tail = raw[idx + len(token) :].strip(" .")
        tail = re.split(r"\s+to\s+", tail, maxsplit=1, flags=re.IGNORECASE)[0]
        tail = re.sub(r"^(the\s+)?(item|dish)\s+", "", tail, flags=re.IGNORECASE)
        cleaned = tail.strip(" .")
        if cleaned:
            return cleaned
    return None


def _parse_price(raw: str) -> tuple[str | None, float | int | None]:
    match = _PRICE.search(raw)
    amount = coerce_price(next((group for group in match.groups() if group), None)) if match else None
    before = raw[: match.start()] if match else raw
    before = re.sub(r"^(change|set|update|make|increase|raise|reduce)\s+", "", before, flags=re.IGNORECASE)
    before = re.sub(r"^(the\s+)?(price\s+of\s+)?", "", before, flags=re.IGNORECASE)
    before = re.sub(r"\b(price|of|for|to|the)\b", " ", before, flags=re.IGNORECASE)
    item = _COLLAPSE.sub(" ", before).strip(" .")
    return (item or None, amount)


def _parse_rename(raw: str, quoted: list[str]) -> tuple[str | None, str | None]:
    if len(quoted) >= 2:
        return quoted[0], quoted[1]
    text = re.sub(r"^(rename|change the name of)\s+", "", raw, flags=re.IGNORECASE)
    parts = re.split(r"\s+to\s+", text, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None, None
    return parts[0].strip(" .") or None, parts[1].strip(" .") or None


def _parse_move(raw: str) -> tuple[str | None, str | None, str | None]:
    text = re.sub(r"^move\s+", "", raw, flags=re.IGNORECASE)
    from_split = re.split(r"\s+from\s+", text, maxsplit=1, flags=re.IGNORECASE)
    if len(from_split) == 2:
        item = from_split[0].strip()
        to_split = re.split(r"\s+to\s+", from_split[1], maxsplit=1, flags=re.IGNORECASE)
        source = to_split[0].strip() or None
        target = to_split[1].strip(" .") if len(to_split) == 2 else None
        return item or None, source, target
    to_split = re.split(r"\s+to\s+", text, maxsplit=1, flags=re.IGNORECASE)
    item = to_split[0].strip() or None
    target = to_split[1].strip(" .") if len(to_split) == 2 else None
    return item, None, target


def _parse_add(raw: str) -> tuple[str | None, str | None, float | int | None]:
    match = _PRICE.search(raw)
    amount = coerce_price(next((group for group in match.groups() if group), None)) if match else None
    body = re.sub(r"^add\s+", "", raw, flags=re.IGNORECASE)
    category = None
    for splitter in (r"\s+to\s+", r"\s+in\s+", r"\s+under\s+"):
        parts = re.split(splitter, body, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            body, category = parts[0], parts[1]
            break
    name = _COLLAPSE.sub(" ", body).strip(" .")
    name = re.sub(r"\s+(?:for|at|to)\s+\d+(?:\.\d+)?\s*$", "", name, flags=re.IGNORECASE).strip(" .")
    if category:
        category = re.sub(r"\s+(?:for|at)\s+\d+(?:\.\d+)?\s*$", "", category, flags=re.IGNORECASE)
        category = re.sub(r"^(the\s+)?", "", category.strip(" ."), flags=re.IGNORECASE)
        category = re.sub(r"\b(category|section)$", "", category, flags=re.IGNORECASE).strip()
    return name or None, category or None, amount


def _parse_remove(raw: str) -> tuple[str | None, str | None]:
    text = re.sub(r"^(remove|delete)\s+", "", raw, flags=re.IGNORECASE)
    text = re.sub(r"\b(the\s+)?(item|dish)\b", "", text, flags=re.IGNORECASE)
    parts = re.split(r"\s+from\s+", text, maxsplit=1, flags=re.IGNORECASE)
    item = _COLLAPSE.sub(" ", parts[0]).strip(" .")
    category = None
    if len(parts) == 2:
        category = re.sub(r"\b(category|section)$", "", parts[1].strip(" ."), flags=re.IGNORECASE).strip()
    return item or None, category or None


def _parse_labels(raw: str) -> tuple[str | None, list[str] | None]:
    item = _item_after(raw, ("for", "of"))
    match = re.search(r"\bto\b", raw, flags=re.IGNORECASE)
    if not match:
        return item, None
    tail = raw[match.end() :].strip(" .")
    if item is None:
        item = _item_after(raw[: match.start()], ("for", "of"))
    labels = [part.strip() for part in _LABEL_SPLIT.split(tail) if part.strip()]
    return item, labels or None
