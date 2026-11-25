() => {
  const reject = /best-restaurants|instamart|genie|offers-near-me|food-offer-near-me|\/support|\/terms/i;
  const restRe = /\/city\/[^/]+\/[^/?#]+-rest\d+/i;
  const dineRe = /\/restaurants\/.+\/dineout|\/city\/[^/]+\/.+\/dineout/i;
  const skipZomato = new Set(["dine-out", "order", "collections", "cuisines", "gold", "photos", "reviews", "nightlife", "india", "restaurants", "district"]);
  const items = [];
  const seen = new Set();
  function add(href, name, extra) {
    const url = String(href || "").split("?")[0];
    if (!url || reject.test(url) || seen.has(url)) return;
    seen.add(url);
    items.push({ url, name: (name || "").trim() || null, ...extra });
  }
  function isZomatoVenue(href) {
    try {
      const parsed = new URL(href, location.href);
      if (!parsed.hostname.includes("zomato.com")) return false;
      const parts = parsed.pathname.split("/").filter(Boolean);
      if (parts.length !== 2) return false;
      return !skipZomato.has(parts[1].toLowerCase());
    } catch (e) {
      return false;
    }
  }
  function isMagicpinStore(href) {
    return /magicpin\.in\/.+\/store\/[A-Za-z0-9]+/i.test(href);
  }
  for (const a of document.querySelectorAll("a[href]")) {
    const href = a.href || a.getAttribute("href") || "";
    if (!(restRe.test(href) || dineRe.test(href) || isZomatoVenue(href) || isMagicpinStore(href))) continue;
    if (reject.test(href)) continue;
    const text = (a.innerText || a.textContent || "").replace(/\s+/g, " ").trim();
    const img = a.querySelector("img");
    add(href, text.split("  ")[0], { image_url: img && img.src ? img.src : null });
  }
  return items;
}
