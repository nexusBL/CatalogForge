from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

# Heuristic weights. These are not ML probabilities.
SCORE_WEIGHTS = {
    "repeat": 0.16,
    "text": 0.08,
    "image": 0.12,
    "price": 0.18,
    "description": 0.10,
    "dietary": 0.08,
    "customisation": 0.06,
    "heading": 0.08,
    "similarity": 0.08,
    "menu_context": 0.06,
}

MIN_REPEAT = 3
SCORE_THRESHOLD = 0.34
MAX_TEXT = 400
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
SKIP_TAGS = {"script", "style", "noscript", "svg", "path", "template"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
NAV_TAGS = {"nav", "header", "footer"}
PRICE_RE = re.compile(r"(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d{1,2})?", re.I)
PRICE_NUM_RE = re.compile(r"[\d,]+(?:\.\d{1,2})?")
DELIVERY_RE = re.compile(r"\b\d+\s*(?:mins?|min)\b", re.I)
DISTANCE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*km\b", re.I)
RELATED_RE = re.compile(r"\brelated to\b|\bmore restaurants\b|\bpeople also\b|\bsimilar restaurants\b", re.I)
CUSTOM_RE = re.compile(r"customis|customiz|add-?on|add ons", re.I)
VEG_RE = re.compile(r"\b(?:veg|vegetarian|pure veg)\b", re.I)
NONVEG_RE = re.compile(r"\b(?:non[\s-]?veg|nonvegetarian|egg)\b", re.I)
SKIP_NAME_RE = re.compile(
    r"^(?:veg|non[\s-]?veg|bestseller|must try|recommended|customise|customize|add ons?|add\+)$",
    re.I,
)
BESTSELLER_RE = re.compile(r"\bbestseller\b|\bmust try\b|\brecommended\b", re.I)
OFFER_RE = re.compile(r"\d+\s*%\s*off|\boffer\b", re.I)


@dataclass(eq=False)
class DomNode:
    tag: str
    attrs: dict[str, str]
    children: list[Any] = field(default_factory=list)
    parent: DomNode | None = None

    def append(self, child: Any) -> None:
        if isinstance(child, DomNode):
            child.parent = self
        self.children.append(child)

    def iter(self):
        yield self
        for child in self.children:
            if isinstance(child, DomNode):
                yield from child.iter()

    def child_nodes(self) -> list[DomNode]:
        return [c for c in self.children if isinstance(c, DomNode)]

    def text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif isinstance(child, DomNode) and child.tag not in SKIP_TAGS:
                parts.append(child.text())
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    def attr(self, name: str) -> str | None:
        return self.attrs.get(name) or self.attrs.get(name.lower())

    def signature(self) -> str:
        bits = [self.tag]
        if any(n.tag in HEADING_TAGS or n.tag == "strong" for n in self.iter()):
            bits.append("title")
        if PRICE_RE.search(self.text()):
            bits.append("price")
        return "|".join(bits)

    def find_tag(self, tag: str) -> DomNode | None:
        for node in self.iter():
            if node.tag == tag:
                return node
        return None

    def ancestors(self) -> list[DomNode]:
        out = []
        current = self.parent
        while current is not None:
            out.append(current)
            current = current.parent
        return out


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = DomNode("document", {})
        self._stack = [self.root]
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        node = DomNode(tag, {k.lower(): (v or "") for k, v in attrs})
        self._stack[-1].append(node)
        if tag not in VOID_TAGS:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._stack[-1].append(text)


@dataclass
class ItemSignals:
    has_text: bool = False
    has_image: bool = False
    has_price: bool = False
    has_description: bool = False
    has_dietary: bool = False
    has_customisation: bool = False
    looks_like_restaurant_card: bool = False


@dataclass
class Candidate:
    signature: str
    repeat_count: int
    score: float
    signals: dict[str, float]
    rejected: str | None = None
    sample_names: list[str] = field(default_factory=list)


@dataclass
class DiscoveredItem:
    item_name: str
    category: str | None = None
    description: str | None = None
    price: float | int | None = None
    original_price: float | int | None = None
    currency: str | None = None
    image_url: str | None = None
    rating: float | None = None
    rating_count: int | str | None = None
    veg_nonveg: str | None = None
    bestseller: bool | None = None
    offer: str | None = None
    customisable: bool | None = None
    labels: list[str] = field(default_factory=list)
    variants: list[dict[str, Any]] = field(default_factory=list)
    addons: list[dict[str, Any]] = field(default_factory=list)
    source_item_id: str | None = None
    source_url: str | None = None
    restaurant_name: str | None = None


@dataclass
class DiscoveryResult:
    restaurant_name: str | None
    items: list[DiscoveredItem]
    candidates: list[Candidate]
    selected: Candidate | None
    diagnostics: dict[str, Any]

    @property
    def has_menu(self) -> bool:
        return bool(self.items)


def parse_html(html: str) -> DomNode:
    parser = _TreeParser()
    parser.feed(html or "")
    parser.close()
    return parser.root


def discover_menu(html: str, source_url: str | None = None) -> DiscoveryResult:
    root = parse_html(html)
    restaurant_name = _restaurant_name(root)
    groups = _sibling_groups(root)
    clusters: dict[str, list[tuple[DomNode, list[DomNode]]]] = {}
    for parent, children in groups:
        if len(children) < MIN_REPEAT:
            continue
        signature = _majority_signature(children)
        clusters.setdefault(signature, []).append((parent, children))

    candidates: list[Candidate] = []
    scored_clusters: list[tuple[Candidate, list[tuple[DomNode, list[DomNode]]]]] = []
    for signature, members in clusters.items():
        nodes = [
            node
            for _, children in members
            for node in children
            if node.signature() == signature and node.tag not in HEADING_TAGS | {"p", "span", "br"}
        ]
        if len(nodes) < MIN_REPEAT:
            continue
        candidate = _score_cluster(signature, members, nodes)
        candidates.append(candidate)
        if candidate.rejected is None:
            scored_clusters.append((candidate, members))

    candidates.sort(key=lambda c: (-(c.score), -c.repeat_count, c.signature))
    selected = None
    selected_members: list[tuple[DomNode, list[DomNode]]] = []
    for candidate, members in sorted(scored_clusters, key=lambda pair: (-pair[0].score, -pair[0].repeat_count)):
        if candidate.score >= SCORE_THRESHOLD:
            selected = candidate
            selected_members = members
            break

    items: list[DiscoveredItem] = []
    if selected is not None:
        raw_items = []
        for parent, children in selected_members:
            signature = selected.signature
            heading_map = _headings_for_children(parent, children)
            for child in children:
                if child.signature() != signature:
                    continue
                raw_items.append((child, heading_map.get(id(child))))
        seen: set[tuple[Any, ...]] = set()
        for node, heading in raw_items:
            item = _extract_item(node, heading, restaurant_name, source_url)
            if not item:
                continue
            key = (item.item_name, item.description, item.price, item.image_url)
            if key in seen:
                continue
            seen.add(key)
            items.append(item)

    diagnostics = {
        "url": source_url,
        "method": "dom_discovery",
        "candidate_count": len(candidates),
        "selected_candidate": None
        if selected is None
        else {
            "repeat_count": selected.repeat_count,
            "score": selected.score,
            "signature": selected.signature,
            "signals": selected.signals,
        },
        "categories_detected": len({item.category for item in items if item.category}),
        "items_detected": len(items),
        "rejected_candidates": [
            {
                "repeat_count": c.repeat_count,
                "score": c.score,
                "reason": c.rejected,
            }
            for c in candidates
            if c.rejected
        ][:12],
    }
    return DiscoveryResult(
        restaurant_name=restaurant_name,
        items=items,
        candidates=candidates,
        selected=selected,
        diagnostics=diagnostics,
    )


def discovery_to_dom_menu(result: DiscoveryResult) -> list[dict[str, Any]]:
    grouped: dict[str | None, list[dict[str, Any]]] = {}
    order: list[str | None] = []
    for item in result.items:
        key = item.category
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(_item_dict(item))
    blocks = []
    for key in order:
        blocks.append({"name": key, "items": grouped[key]})
    return blocks


def _item_dict(item: DiscoveredItem) -> dict[str, Any]:
    labels = list(item.labels)
    if item.offer and item.offer not in labels:
        labels.append(item.offer)
    extra = {
        "currency": item.currency,
        "customisable": item.customisable,
        "offer": item.offer,
        "source_item_id": item.source_item_id,
        "source_url": item.source_url,
        "bestseller": item.bestseller,
        "restaurant_name": item.restaurant_name,
        "category": item.category,
    }
    return {
        "name": item.item_name,
        "description": item.description,
        "price": item.price,
        "original_price": item.original_price,
        "image_url": item.image_url,
        "food_type": item.veg_nonveg,
        "rating": item.rating,
        "rating_count": item.rating_count,
        "labels": labels,
        "variants": item.variants,
        "customizations": item.addons,
        "additional_information": {k: v for k, v in extra.items() if v not in (None, "", [], {})},
    }


def _sibling_groups(root: DomNode) -> list[tuple[DomNode, list[DomNode]]]:
    groups = []
    for node in root.iter():
        children = [
            child
            for child in node.child_nodes()
            if child.tag not in {"script", "style", "br", "hr"}
        ]
        if len(children) < MIN_REPEAT:
            continue
        groups.append((node, children))
    return groups


def _majority_signature(children: list[DomNode]) -> str:
    counts: dict[str, int] = {}
    for child in children:
        sig = child.signature()
        counts[sig] = counts.get(sig, 0) + 1
    return max(counts, key=lambda key: (counts[key], -len(key)))


def _score_cluster(
    signature: str,
    members: list[tuple[DomNode, list[DomNode]]],
    nodes: list[DomNode],
) -> Candidate:
    signals_list = [_item_signals(node) for node in nodes]
    n = len(nodes) or 1
    frac = lambda pred: sum(1 for s in signals_list if pred(s)) / n
    restaurant_frac = frac(lambda s: s.looks_like_restaurant_card)
    price_frac = frac(lambda s: s.has_price)
    in_nav = any(_in_chrome(parent) for parent, _ in members)
    related = any(_near_related_heading(parent) for parent, _ in members)
    heading_frac = sum(1 for parent, children in members if _nearest_heading(parent, children[0] if children else parent)) / max(
        len(members), 1
    )
    menu_context = _menu_context_score(members)

    signals = {
        "repeat": min(len(nodes) / 12.0, 1.0),
        "text": frac(lambda s: s.has_text),
        "image": frac(lambda s: s.has_image),
        "price": price_frac,
        "description": frac(lambda s: s.has_description),
        "dietary": frac(lambda s: s.has_dietary),
        "customisation": frac(lambda s: s.has_customisation),
        "heading": min(heading_frac, 1.0),
        "similarity": _similarity_score(nodes),
        "menu_context": menu_context,
    }
    weighted = sum(SCORE_WEIGHTS[key] * signals[key] for key in SCORE_WEIGHTS)
    total_w = sum(SCORE_WEIGHTS.values())
    score = round(weighted / total_w, 4)

    rejected = None
    if in_nav:
        rejected = "navigation_or_chrome"
        score = round(score * 0.15, 4)
    elif related or (restaurant_frac >= 0.5 and price_frac < 0.35):
        rejected = "related_restaurant_cards"
        score = round(score * 0.12, 4)
    elif price_frac < 0.15 and frac(lambda s: s.has_image) < 0.15 and len(nodes) < 8:
        rejected = "too_few_menu_signals"
        score = round(score * 0.4, 4)

    sample = []
    for node in nodes[:5]:
        name = _item_name(node)
        if name:
            sample.append(name)
    return Candidate(
        signature=signature,
        repeat_count=len(nodes),
        score=score,
        signals={k: round(v, 4) for k, v in signals.items()},
        rejected=rejected,
        sample_names=sample,
    )


def _item_signals(node: DomNode) -> ItemSignals:
    text = node.text()
    prices = PRICE_RE.findall(text)
    desc = _item_description(node, _item_name(node))
    dietary = _dietary(node, text)
    custom = bool(CUSTOM_RE.search(text)) or any(
        CUSTOM_RE.search(n.text() or "") for n in node.iter() if n.tag in {"button", "span", "div"}
    )
    restaurant_card = bool(DELIVERY_RE.search(text) and DISTANCE_RE.search(text)) or bool(
        DELIVERY_RE.search(text) and not prices and _looks_like_cuisine_line(text)
    )
    return ItemSignals(
        has_text=len(text) >= 4,
        has_image=node.find_tag("img") is not None,
        has_price=bool(prices),
        has_description=bool(desc),
        has_dietary=dietary is not None,
        has_customisation=bool(custom),
        looks_like_restaurant_card=restaurant_card,
    )


def _looks_like_cuisine_line(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]+,\s*[A-Za-z]+", text)) and bool(
        re.search(r"\b(?:indian|chinese|pizza|biryani|south|north|fast food|cafe|italian)\b", text, re.I)
    )


def _similarity_score(nodes: list[DomNode]) -> float:
    if not nodes:
        return 0.0
    sigs = [node.signature() for node in nodes]
    majority = max(set(sigs), key=sigs.count)
    return sigs.count(majority) / len(sigs)


def _in_chrome(node: DomNode) -> bool:
    for ancestor in [node, *node.ancestors()]:
        if ancestor.tag in NAV_TAGS:
            return True
        role = (ancestor.attr("role") or "").lower()
        if role in {"navigation", "banner", "contentinfo"}:
            return True
    return False


def _near_related_heading(node: DomNode) -> bool:
    heading = _previous_heading(node)
    if heading and RELATED_RE.search(heading):
        return True
    for child in node.child_nodes()[:8]:
        text = _as_heading(child)
        if text and RELATED_RE.search(text):
            return True
    labeled = node.attr("aria-label") or ""
    return bool(RELATED_RE.search(labeled))


def _menu_context_score(members: list[tuple[DomNode, list[DomNode]]]) -> float:
    texts = []
    for parent, _ in members:
        heading = _previous_heading(parent) or ""
        texts.append(heading)
        texts.append(parent.attr("aria-label") or "")
    blob = " ".join(texts).lower()
    if RELATED_RE.search(blob):
        return 0.0
    if any(word in blob for word in ("menu", "item", "category", "recommended")):
        return 1.0
    if any(_previous_heading(parent) for parent, _ in members):
        return 0.7
    return 0.35


def _headings_for_children(parent: DomNode, children: list[DomNode]) -> dict[int, str | None]:
    current: str | None = _nearest_heading(parent, children[0] if children else parent)
    mapping: dict[int, str | None] = {}
    for child in parent.child_nodes():
        heading_text = _as_heading(child)
        if heading_text:
            current = heading_text
            continue
        if child in children:
            mapping[id(child)] = current
    return mapping


def _as_heading(node: DomNode) -> str | None:
    if node.tag in HEADING_TAGS or (node.attr("role") or "").lower() == "heading":
        text = node.text()
        if 1 < len(text) <= 80 and not PRICE_RE.search(text):
            return text
    return None


def _nearest_heading(parent: DomNode, child: DomNode) -> str | None:
    heading = _previous_heading(child) or _previous_heading(parent)
    if heading and not RELATED_RE.search(heading):
        return heading
    return heading if heading and not RELATED_RE.search(heading) else None


def _previous_heading(node: DomNode) -> str | None:
    current = node
    while current is not None and current.parent is not None:
        siblings = current.parent.child_nodes()
        idx = next((i for i, sib in enumerate(siblings) if sib is current), -1)
        for sib in reversed(siblings[:idx]):
            text = _as_heading(sib)
            if text:
                return text
            nested = None
            for desc in sib.iter():
                nested = _as_heading(desc)
                if nested:
                    return nested
        current = current.parent
    return None


def _restaurant_name(root: DomNode) -> str | None:
    for node in root.iter():
        if node.tag == "meta" and (node.attr("property") or "").lower() == "og:title":
            content = (node.attr("content") or "").split("|")[0].split("-")[0].strip()
            if content:
                return content
        if node.tag == "h1":
            text = node.text()
            if text:
                return text
    for node in root.iter():
        if node.tag == "title":
            text = node.text().split("|")[0].split("-")[0].strip()
            return text or None
    return None


def _extract_item(
    node: DomNode,
    heading: str | None,
    restaurant_name: str | None,
    source_url: str | None,
) -> DiscoveredItem | None:
    name = _item_name(node)
    if not name:
        return None
    text = node.text()
    if RELATED_RE.search(text) or _item_signals(node).looks_like_restaurant_card:
        return None
    description = _item_description(node, name)
    price, original, currency = _prices(node)
    image = _image_url(node, source_url)
    dietary = _dietary(node, text)
    custom = True if CUSTOM_RE.search(text) else None
    offer = None
    offer_match = OFFER_RE.search(text)
    if offer_match:
        offer = offer_match.group(0)
    label_hits = [match.group(0) for match in BESTSELLER_RE.finditer(text)]
    bestseller = True if any("bestseller" in hit.lower() for hit in label_hits) else None
    rating, rating_count = _rating(text)
    variants = []
    addons = []
    if custom:
        addons.append({"present": True})
    source_id = node.attr("data-item-id") or node.attr("id")
    category = heading if heading and not RELATED_RE.search(heading) else None
    return DiscoveredItem(
        item_name=name,
        category=category,
        description=description,
        price=price,
        original_price=original,
        currency=currency,
        image_url=image,
        rating=rating,
        rating_count=rating_count,
        veg_nonveg=dietary,
        bestseller=bestseller,
        offer=offer,
        customisable=custom,
        labels=list(dict.fromkeys(label_hits)),
        variants=variants,
        addons=addons,
        source_item_id=source_id,
        source_url=source_url,
        restaurant_name=restaurant_name,
    )


def _item_name(node: DomNode) -> str | None:
    named = node.attr("data-item-name")
    if named and 2 <= len(named) <= 80 and not PRICE_RE.search(named):
        return _clean(named)
    for tag in ("h3", "h4", "h5", "strong"):
        found = node.find_tag(tag)
        if found:
            text = _clean(found.text())
            if 2 <= len(text) <= 80 and not PRICE_RE.search(text) and not SKIP_NAME_RE.match(text):
                return text
    for line in _text_lines(node):
        if 2 <= len(line) <= 80 and not PRICE_RE.search(line) and not DELIVERY_RE.search(line) and not SKIP_NAME_RE.match(line):
            return line
    return None


def _item_description(node: DomNode, name: str | None) -> str | None:
    for child in node.iter():
        if child.tag == "p":
            text = _clean(child.text())
            if text and text != name and len(text) >= 8 and not PRICE_RE.fullmatch(text):
                return text[:MAX_TEXT]
    lines = [line for line in _text_lines(node) if line != name and not PRICE_RE.search(line)]
    if len(lines) >= 2:
        desc = lines[1]
        if len(desc) >= 8:
            return desc[:MAX_TEXT]
    return None


def _text_lines(node: DomNode) -> list[str]:
    lines = []
    for child in node.children:
        if isinstance(child, str):
            text = _clean(child)
            if text:
                lines.append(text)
        elif isinstance(child, DomNode) and child.tag not in SKIP_TAGS:
            text = _clean(child.text())
            if text:
                lines.append(text)
    return lines


def _prices(node: DomNode) -> tuple[float | int | None, float | int | None, str | None]:
    text = node.text()
    matches = list(PRICE_RE.finditer(text))
    currency = None
    if "₹" in text:
        currency = "INR"
    elif re.search(r"\brs\.?\b", text, re.I):
        currency = "INR"
    amounts = [_parse_amount(m.group(0)) for m in matches]
    amounts = [a for a in amounts if a is not None]
    strike = None
    for desc in node.iter():
        if desc.tag in {"s", "del", "strike"}:
            strike = _parse_amount(desc.text())
            break
    if not amounts:
        return None, strike, currency
    price = amounts[0]
    original = strike if strike and strike != price else (amounts[1] if len(amounts) > 1 else None)
    return price, original, currency


def _parse_amount(value: str) -> float | int | None:
    num = PRICE_NUM_RE.search(value.replace(",", ""))
    if not num:
        return None
    raw = num.group(0)
    amount = float(raw) if "." in raw else int(raw)
    if isinstance(amount, float) and amount.is_integer():
        return int(amount)
    return amount


def _image_url(node: DomNode, source_url: str | None) -> str | None:
    img = node.find_tag("img")
    if not img:
        return None
    src = img.attr("src") or img.attr("data-src") or img.attr("data-lazy-src")
    if not src or src.startswith("data:"):
        return None
    if source_url and src.startswith("/"):
        return urljoin(source_url, src)
    return src


def _dietary(node: DomNode, text: str) -> str | None:
    blob = " ".join(
        filter(
            None,
            [
                text,
                node.attr("aria-label"),
                node.attr("title"),
                *[img.attr("alt") or "" for img in node.iter() if img.tag == "img"],
            ],
        )
    )
    if NONVEG_RE.search(blob):
        return "NONVEG"
    if VEG_RE.search(blob):
        return "VEG"
    labeled = node.attr("data-veg-classifier") or node.attr("data-food-type")
    if labeled:
        return labeled.strip().upper()
    return None


def _rating(text: str) -> tuple[float | None, str | None]:
    match = re.search(r"\b([1-5](?:\.\d)?)\s*(?:\((\d+[+]?)\)|★|stars?)?", text)
    if not match:
        return None, None
    # Avoid treating prices like 399 as ratings.
    value = float(match.group(1))
    if value > 5:
        return None, None
    return value, match.group(2)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(value or "")).strip()
