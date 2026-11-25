async (opts) => {
  const verifyQuery = ((opts && (opts.verify || opts.query)) || "").trim();
  const query = ((opts && (opts.type || opts.query)) || "").trim();
  const platform = ((opts && opts.platform) || "").toLowerCase();
  const category = (opts && opts.category) || "";
  const city = ((opts && opts.city) || "").trim();
  const state = ((opts && opts.state) || "").trim();
  const locality = ((opts && opts.locality) || "").trim();
  function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
  function visible(el) {
    if (!el) return false;
    const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    if (style && (style.display === "none" || style.visibility === "hidden")) return false;
    const box = el.getBoundingClientRect ? el.getBoundingClientRect() : { width: 1, height: 1 };
    return box.width > 0 && box.height > 0;
  }
  function textOf(el) {
    return el ? String(el.innerText || el.textContent || "").replace(/\s+/g, " ").trim() : "";
  }
  function fold(value) {
    return String(value || "").toLowerCase().replace(/[,\s/|]+/g, " ").replace(/bengaluru/g, "bangalore").replace(/mangaluru/g, "mangalore").trim();
  }
  function tokens(value) {
    return String(value || "").toLowerCase().split(/[,\s/|]+/).map((part) => part.trim()).filter((part) => part.length > 1);
  }
  function placeKey(value) {
    return fold(value).replace(/[^a-z0-9]+/g, "");
  }
  function hasLocality(hay, loc) {
    if (!loc) return true;
    if (hay.includes(loc)) return true;
    const key = placeKey(loc);
    return Boolean(key) && placeKey(hay).includes(key);
  }
  function cityAliases(name) {
    const c = fold(name).trim();
    if (!c) return [];
    if (c === "bangalore" || c === "bengaluru") return ["bangalore", "bengaluru"];
    if (c === "mangalore" || c === "mangaluru") return ["mangalore", "mangaluru"];
    return [c];
  }
  function containsCity(hay, name) {
    const aliases = cityAliases(name);
    if (!aliases.length) return true;
    const folded = fold(hay);
    return aliases.some((alias) => folded.includes(alias));
  }
  function suggestionHead(text) {
    const hay = fold(text);
    let cut = hay.length;
    for (const alias of cityAliases(city).concat(["bangalore", "bengaluru"])) {
      const index = hay.indexOf(alias);
      if (index >= 0 && index < cut) cut = index;
    }
    return hay.slice(0, cut).replace(/^[, ]+|[, ]+$/g, "");
  }
  function isTopLevel(text) {
    if (rankSuggestion(text) == null) return false;
    const loc = fold(locality);
    if (!loc) return Boolean(city) && containsCity(text, city);
    if (placeKey(suggestionHead(text)) !== placeKey(loc)) return false;
    if (city && !containsCity(text, city)) return false;
    return true;
  }
  function looksLikeCuisine(text) {
    return /sandwich|salad|wrap|healthy food|biryani|kebab|barbecue|north indian|south indian|chinese|snacks|street food/i.test(text);
  }
  function rankSuggestion(text) {
    const raw = String(text || "").replace(/\s+/g, " ").trim();
    if (!raw || raw.length > 180) return null;
    const hay = fold(raw);
    if (looksLikeCuisine(raw)) return null;
    if (/\b(restaurant|cafe|hotel|dhaba|kitchen|pizza|burger|bar|lounge|bakery|nandos|kfc|domino)\b/i.test(raw)) return null;
    const loc = fold(locality);
    if (/\b(road|rd\.?|street|cross)\b/i.test(raw) && !/road|street/.test(loc)) return null;
    if (/\b(\d+)(?:st|nd|rd|th)?\s*phase\b/i.test(raw) && !/phase/.test(loc)) return null;
    if (loc && !hasLocality(hay, loc)) return null;
    if (city && !containsCity(hay, city) && !(loc && hasLocality(hay, loc))) return null;
    if (city && !loc && !containsCity(hay, city)) return null;
    let score = scoreText(raw, tokens(verifyQuery || query));
    if (loc && hasLocality(hay, loc)) score += 6;
    if (city && containsCity(hay, city)) score += 4;
    if (state && hay.includes(fold(state))) score += 2;
    if (/,/.test(raw)) score += 1;
    return score > 0 ? score : null;
  }
  function scoreText(text, wanted) {
    const hay = fold(text);
    if (!hay) return 0;
    let score = 0;
    for (const token of wanted) {
      if (hay.includes(fold(token))) score += 1;
    }
    if (locality && hasLocality(hay, fold(locality))) score += 3;
    if (city && containsCity(hay, city)) score += 3;
    if (state && hay.includes(fold(state))) score += 1;
    if (city && !containsCity(hay, city) && !(locality && hasLocality(hay, fold(locality)))) score -= 12;
    return score;
  }
  function isVenueSearch(el) {
    const blob = `${el.getAttribute("placeholder") || ""} ${el.getAttribute("aria-label") || ""} ${el.getAttribute("name") || ""}`.toLowerCase();
    return blob.includes("restaurant") || blob.includes("cuisine") || blob.includes("dish") || blob.includes("places, cuisines") || (blob.includes("search for") && blob.includes("food"));
  }
  async function typeQuery(el, value) {
    if (!el) return false;
    el.focus();
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    const setVal = (next) => {
      if (desc && desc.set) desc.set.call(el, next);
      else el.value = next;
    };
    setVal("");
    el.dispatchEvent(new Event("input", { bubbles: true }));
    for (const ch of value) {
      setVal((el.value || "") + ch);
      el.dispatchEvent(new InputEvent("input", { bubbles: true, composed: true, data: ch, inputType: "insertText" }));
      el.dispatchEvent(new KeyboardEvent("keydown", { key: ch, bubbles: true }));
      el.dispatchEvent(new KeyboardEvent("keyup", { key: ch, bubbles: true }));
      await sleep(50);
    }
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }
  function locationInput() {
    const preferred = [
      "input.location",
      "input[placeholder*='Search Location' i]",
      "input[placeholder*='delivery location' i]",
      "input[placeholder*='area, street' i]",
      "input[placeholder*='street name' i]",
      "input[placeholder*='Detect my location' i]",
      "input[aria-label*='location' i]",
      "input[placeholder*='location' i]",
    ];
    for (const sel of preferred) {
      const el = document.querySelector(sel);
      if (el && visible(el) && !isVenueSearch(el)) return el;
    }
    const active = document.activeElement;
    if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA") && visible(active) && !isVenueSearch(active)) {
      return active;
    }
    const nodes = Array.from(document.querySelectorAll("input, textarea"));
    const ranked = nodes.filter((el) => visible(el)).map((el) => {
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      const aria = (el.getAttribute("aria-label") || "").toLowerCase();
      const name = (el.getAttribute("name") || el.className || "").toLowerCase();
      const blob = `${ph} ${aria} ${name}`;
      let rank = 0;
      if (isVenueSearch(el)) rank -= 20;
      if (blob.includes("location") || blob.includes("area") || blob.includes("street") || blob.includes("locality") || blob.includes("city") || blob.includes("detect")) rank += 10;
      return { el, rank };
    });
    ranked.sort((a, b) => b.rank - a.rank);
    const hit = ranked.find((item) => item.rank > 0);
    return (hit && hit.el) || null;
  }
  function headerSkip(text) {
    return /^(cart|sign in|log in|help|offers|search|swiggy corporate|zomato|magicpin|new|\d+|login|signup)$/i.test(text);
  }
  function clickBySelectors(selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && (visible(el) || sel === ".selectedLocation")) {
        try { el.click(); } catch (e) {}
        return true;
      }
    }
    return false;
  }
  function clickHeaderLocation() {
    const skip = /^(cart|sign in|help|offers|search|swiggy corporate|new|\d+)$/i;
    const headerHit = Array.from(document.querySelectorAll("div,span,button,a,p")).find((node) => {
      if (!visible(node)) return false;
      const box = node.getBoundingClientRect ? node.getBoundingClientRect() : { top: 0, left: 0 };
      if (box.top > 96 || box.left > 520) return false;
      const text = textOf(node);
      if (!text || text.length > 80 || skip.test(text) || headerSkip(text)) return false;
      if (/search for restaurant|search for places|swiggy corporate/i.test(text)) return false;
      if (/biryani|kebab|barbecue|north indian|south indian|chinese|snacks|street food/i.test(text)) return false;
      if ((text.match(/,/g) || []).length >= 3 && /indian|food|grill/i.test(text)) return false;
      return true;
    });
    if (headerHit) {
      try { headerHit.click(); } catch (e) {}
      return true;
    }
    return false;
  }
  function clickBetweenLandmarks(leftNeedles, rightNeedles) {
    const nodes = Array.from(document.querySelectorAll("a, button, div, span, p, img")).filter(visible);
    function findNeedle(needles) {
      return nodes.find((node) => {
        const text = textOf(node).toLowerCase();
        const alt = String(node.getAttribute && node.getAttribute("alt") || "").toLowerCase();
        const href = String(node.getAttribute && node.getAttribute("href") || node.href || "").toLowerCase();
        return needles.some((needle) => text === needle || text.includes(needle) || alt.includes(needle) || href.includes(needle));
      });
    }
    const left = findNeedle(leftNeedles);
    const right = findNeedle(rightNeedles);
    const leftBox = left ? left.getBoundingClientRect() : { right: 8, top: 8, bottom: 72 };
    const rightBox = right ? right.getBoundingClientRect() : { left: 420, top: 8 };
    const candidates = Array.from(document.querySelectorAll("div, span, button, a, p")).filter((node) => {
      if (!visible(node)) return false;
      const box = node.getBoundingClientRect();
      if (box.top > 92 || box.height > 80) return false;
      if (box.left < leftBox.right - 4) return false;
      if (box.left >= rightBox.left - 2) return false;
      const text = textOf(node);
      if (!text || text.length > 90) return false;
      if (headerSkip(text) || looksLikeCuisine(text)) return false;
      if (/search for restaurant|search for places|corporate/i.test(text)) return false;
      return true;
    });
    const preferred = candidates.find((node) => /,/.test(textOf(node))) || candidates[0];
    if (!preferred) return false;
    try { preferred.click(); } catch (e) { return false; }
    return true;
  }
  function clickLocationControl() {
    if (platform === "swiggy" && clickBetweenLandmarks(["swiggy"], ["swiggy corporate"])) return true;
    if (platform === "zomato" && clickBetweenLandmarks(["zomato"], ["search for restaurant", "search for cuisine"])) return true;
    if (platform === "magicpin" && clickBetweenLandmarks(["magicpin"], ["search for places", "cuisines, and more"])) return true;
    const semantic = [
      "button[aria-label*='location' i]",
      "[aria-label*='change location' i]",
      "[aria-label*='select location' i]",
      "input[aria-label*='location' i]",
      "[role='combobox'][aria-label*='location' i]",
    ];
    if (clickBySelectors(semantic)) return true;
    if (platform === "magicpin" && clickBySelectors([".selectedLocation", "[class*='selectedLocation']", "input.location"])) return true;
    if (platform === "zomato" && clickBySelectors(["[class*='locationDropDown']", "[class*='header-location']"])) return true;
    if (platform === "swiggy" && clickBySelectors(["[class*='LocationContainer']", "[class*='LocationContentBlock']", "[class*='LocationContent']"])) return true;
    const fallback = [
      ".selectedLocation",
      "[class*='selectedLocation']",
      "input.location",
      "[class*='LocationContainer']",
      "[class*='LocationContentBlock']",
      "[class*='locationDropDown']",
      "[class*='header-location']",
    ];
    if (clickBySelectors(fallback)) return true;
    const needles = [
      "search location",
      "setup your precise location",
      "precise location",
      "select location",
    ];
    const nodes = Array.from(document.querySelectorAll("a, button, div, span, p"));
    const hit = nodes.find((node) => {
      if (!visible(node)) return false;
      const text = textOf(node).toLowerCase();
      if (!text || text.length > 80) return false;
      return needles.some((needle) => text === needle || text.includes(needle));
    });
    if (hit) {
      try { hit.click(); } catch (e) {}
      return true;
    }
    return clickHeaderLocation();
  }
  function suggestionNodes() {
    const picked = [];
    const selectors = "[role='option'], [role='listbox'] [role='option'], [class*='Location-sc-'], [class*='LocationBlock'], [class*='LocationContent'], [class*='suggestion' i], [class*='autoComplete' i], [class*='autocomplete' i], [class*='place-item' i], [class*='location-item' i], div, span";
    for (const node of document.querySelectorAll(selectors)) {
      if (!visible(node)) continue;
      const box = node.getBoundingClientRect();
      if (box.top < 48 || box.height > 90) continue;
      const text = textOf(node);
      if (text && text.length >= 8 && text.length < 180) picked.push(node);
    }
    picked.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
    return picked;
  }
  function clickSuggestion() {
    const wanted = tokens(query);
    if (!wanted.length) return { ok: false, text: "" };
    const seen = new Set();
    for (const node of suggestionNodes()) {
      const text = textOf(node);
      if (!text || seen.has(text)) continue;
      seen.add(text);
      if (isTopLevel(text)) {
        try { node.click(); } catch (e) { return { ok: false, text }; }
        return { ok: true, text };
      }
    }
    let best = null;
    let bestScore = -999;
    let bestText = "";
    for (const node of suggestionNodes()) {
      const text = textOf(node);
      const score = rankSuggestion(text);
      if (score == null) continue;
      if (score > bestScore) {
        bestScore = score;
        best = node;
        bestText = text;
      }
    }
    if (!best) return { ok: false, text: "" };
    try { best.click(); } catch (e) { return { ok: false, text: bestText }; }
    return { ok: true, text: bestText };
  }
  function displayedLocation() {
    const skipLine = /^(other|setup your precise location|precise location|select location|search location|search for restaurant|search for places|cart|sign in|help|offers|search|swiggy corporate|new|\d+)$/i;
    function looksLikeCuisine(text) {
      return /sandwich|salad|wrap|healthy food|biryani|kebab|barbecue|north indian|south indian|chinese|snacks|street food/i.test(text);
    }
    function pick(raw) {
      const wanted = tokens(query);
      const lines = String(raw || "").split(/\n/).map((s) => s.replace(/\s+/g, " ").trim()).filter(Boolean);
      const usable = lines.filter((line) => !skipLine.test(line) && line.length < 180 && !looksLikeCuisine(line));
      const matched = wanted.length ? usable.filter((line) => scoreText(line, wanted) > 0) : [];
      const pool = matched.length ? matched : usable;
      const addr = pool.find((line) => line.includes(",") && (/india/i.test(line) || wanted.some((token) => fold(line).includes(fold(token)))));
      if (addr) return addr;
      return pool.find((line) => line.length > 2 && line.length < 80) || "";
    }
    if (platform === "magicpin") {
      const el = document.querySelector(".selectedLocation, [class*='selectedLocation']");
      const got = pick(textOf(el));
      if (got) return got;
    }
    const selectors = [
      "button[aria-label*='location' i]",
      "[aria-label*='location' i]",
      "[class*='LocationContent']",
      "[class*='LocationContainer']",
      "[class*='LocationBlock']",
      ".selectedLocation",
      "[class*='selectedLocation']",
      "[class*='locationDropDown']",
      "[class*='header-location']",
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      const got = pick(el ? (el.innerText || el.textContent || "") : "");
      if (got && !/search for restaurant|search for places/i.test(got)) return got;
    }
    const header = Array.from(document.querySelectorAll("header, nav, [role='banner'], div, span, button, a, p")).find((node) => {
      if (!visible(node)) return false;
      const box = node.getBoundingClientRect ? node.getBoundingClientRect() : { top: 0, left: 0 };
      if (box.top > 96 || box.left > 520) return false;
      return Boolean(pick(node.innerText || node.textContent || ""));
    });
    return header ? pick(header.innerText || header.textContent || "") : "";
  }
  function clickCategory() {
    if (!category) return false;
    const need = category.toLowerCase();
    const alts = {
      "food delivery": ["food delivery", "food-delivery", "/restaurants"],
      "dineout": ["dineout", "/dineout", "offers-near-me"],
      "budget dining": ["budget dining", "budget eats"],
      "fine dining": ["fine dining", "fine-dine"],
    };
    const needles = alts[need] || [need];
    const cards = Array.from(document.querySelectorAll("a.discovery-link, a[href*='category'], a, button, div"));
    const card = cards.find((node) => {
      if (!visible(node) && node.tagName !== "A") return false;
      const img = node.querySelector && node.querySelector("img");
      const alt = ((img && img.alt) || "").toLowerCase();
      const href = String(node.href || node.getAttribute("href") || "").toLowerCase();
      const text = textOf(node).toLowerCase();
      const blob = `${alt} ${text} ${href}`;
      return needles.some((needle) => blob.includes(needle)) && (text === need || text.startsWith(need) || alt.includes(need.split(" ")[0]) || href.includes("category") || text.length < 40);
    });
    if (card) {
      const target = card.closest ? (card.closest("a") || card) : card;
      try { target.click(); } catch (e) {}
      return true;
    }
    return false;
  }
  const phase = (opts && opts.phase) || "all";
  if (phase === "read") {
    return { ok: true, query, displayed: displayedLocation(), href: location.href, phase };
  }
  if (!query) return { ok: false, query, category, reason: "empty" };
  let picked = false;
  let selectedText = "";
  if (phase === "location" || phase === "all") {
    clickLocationControl();
    await sleep(500);
    const input = locationInput();
    if (input) {
      input.focus();
      input.select && input.select();
    }
    await typeQuery(input, query);
    await sleep(1100);
    let choice = clickSuggestion();
    if (!choice.ok) {
      await sleep(900);
      choice = clickSuggestion();
    }
    picked = choice.ok;
    selectedText = choice.text || "";
    await sleep(400);
    if (phase === "location") {
      return { ok: picked, query, category, picked, selectedText, displayed: displayedLocation(), href: location.href, phase };
    }
  }
  await sleep(900);
  const categoryClicked = (phase === "category" || phase === "all") ? clickCategory() : false;
  await sleep(800);
  return { ok: picked || categoryClicked, query, category, picked, selectedText, displayed: displayedLocation(), categoryClicked, href: location.href, phase };
}
