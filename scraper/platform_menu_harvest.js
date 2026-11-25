async () => {
    function abs(url) {
        if (!url || String(url).startsWith("data:")) return null;
        try { return new URL(String(url), location.href).href; } catch (e) { return String(url); }
    }
    function unwrap(url) {
        const raw = abs(url);
        if (!raw) return null;
        const match = /[?&]url=([^&]+)/i.exec(raw);
        if (match) {
            try { return abs(decodeURIComponent(match[1])); } catch (e) { return raw; }
        }
        return raw;
    }
    function fromSrcset(value) {
        if (!value) return null;
        const parts = String(value).split(",").map((part) => part.trim().split(/\s+/)[0]).filter(Boolean);
        return parts.length ? unwrap(parts[parts.length - 1]) : null;
    }
    function attrUrl(el) {
        if (!el || !el.getAttribute) return null;
        return unwrap(
            el.currentSrc
            || el.src
            || el.getAttribute("src")
            || el.getAttribute("data-src")
            || el.getAttribute("data-original")
            || el.getAttribute("data-lazy-src")
            || el.getAttribute("data-bg")
            || fromSrcset(el.getAttribute("srcset") || el.getAttribute("data-srcset"))
        );
    }
    function bgUrl(el) {
        if (!el) return null;
        const style = (el.getAttribute && el.getAttribute("style")) || "";
        let match = /url\((['"]?)(https?:[^'")]+)\1\)/i.exec(style);
        if (match) return unwrap(match[2]);
        try {
            const computed = getComputedStyle(el).backgroundImage || "";
            match = /url\((['"]?)(https?:[^'")]+)\1\)/i.exec(computed);
            if (match) return unwrap(match[2]);
        } catch (e) {}
        return null;
    }
    function isJunk(url) {
        return /veg-icon|non-veg-icon|egg-icon|star-filled|star-empty|star-|web_assets|placeholder|logo|favicon|s120\b|=s120\b|=w120\b|=w200-rw|sprite|avatar|app-store|play-store|merchant_app|badge|rating_|\/images\/merchant\/|\/images\/icons\//i.test(url || "");
    }
    function isFoodImage(url) {
        if (!url || isJunk(url)) return false;
        if (/dish_photos|mpcdn|im1\.magicpin|magicpin|swiggy|zmtcdn|cloudinary|googleusercontent|lh3\.googleusercontent/i.test(url)) return true;
        if (/\.(jpg|jpeg|png|webp|avif)($|\?)/i.test(url) && !/icon|logo|avatar|button/i.test(url)) return true;
        return false;
    }
    function isInvalidCategoryName(name) {
        if (!name) return true;
        const clean = String(name).trim();
        if (/^\d+(\.\d+)?$/.test(clean)) return true;
        if (/^(overview|offers|delivery|dineout|menu|reviews|photos|order online|search|rating|ratings|about|help|login|signup)$/i.test(clean)) return true;
        return false;
    }
    function foodImgUrl(el) {
        if (!el) return null;
        const extra = el.querySelectorAll ? el.querySelectorAll("img, source, picture, [style], [data-src], [data-original]") : [];
        const nodes = [el, ...extra];
        for (const node of nodes) {
            const url = attrUrl(node) || bgUrl(node);
            if (isFoodImage(url)) return url;
        }
        return null;
    }
    function linesOf(el) {
        return String((el && el.innerText) || "")
            .split("\n")
            .map((line) => line.replace(/\s+/g, " ").trim())
            .filter(Boolean);
    }
    function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

    const host = (location.hostname || "").toLowerCase();
    const categories = [];
    const images = [];
    const seenImg = new Set();

    function pushImage(url, alt) {
        if (!isFoodImage(url) || seenImg.has(url)) return;
        seenImg.add(url);
        images.push({ url, alt: alt || "", category: "food" });
    }
    function addCategory(name, count) {
        let title = String(name || "").replace(/\s+\(\d+\)\s*$/, "").trim();
        if (isInvalidCategoryName(title)) {
            return categories.length ? categories[categories.length - 1] : null;
        }
        let current = categories.find((item) => item.name.toLowerCase() === title.toLowerCase());
        if (!current) {
            current = { name: title, items: [], item_count: count == null ? null : Number(count) };
            categories.push(current);
        } else if (count != null && current.item_count == null) {
            current.item_count = Number(count);
        }
        return current;
    }
    function addItem(category, item) {
        if (!item || !item.name) return;
        const bucket = category || addCategory("Menu");
        if (bucket.items.some((existing) => existing.name.toLowerCase() === item.name.toLowerCase())) return;
        if (item.image_url && !isFoodImage(item.image_url)) item.image_url = null;
        bucket.items.push(item);
        if (item.image_url) pushImage(item.image_url, item.name);
    }
    function parseCard(card, foodHint) {
        const lines = linesOf(card);
        const prices = [];
        for (const line of lines) {
            const match = line.match(/^₹\s*([\d,]+)/);
            if (match) prices.push(Number(match[1].replace(/,/g, "")));
        }
        const name = lines.find((line) =>
            line.length >= 3
            && line.length < 80
            && !/^₹/.test(line)
            && !/^(add|bestseller|customizable|veg|non-veg|read more)$/i.test(line)
            && !/items?$/i.test(line)
            && !/dish_photos|search within menu/i.test(line)
            && /[A-Za-z]/.test(line)
        );
        if (!name) return null;
        const description = lines.find((line) => line !== name && (line.length > 48 || /served|cooked|read more/i.test(line)));
        return {
            name,
            description: description || null,
            price: prices.length ? Math.min(...prices) : null,
            original_price: prices.length > 1 ? Math.max(...prices) : null,
            image_url: foodImgUrl(card),
            food_type: foodHint || null,
            is_bestseller: /bestseller/i.test(card.innerText || ""),
        };
    }
    function yOf(el) {
        if (!el) return 0;
        const rect = el.getBoundingClientRect();
        return rect.top + window.scrollY;
    }
    function contentHeading(name) {
        const target = String(name || "").replace(/\s+/g, " ").trim().toLowerCase();
        if (!target) return null;
        return [...document.querySelectorAll("h2,h3,h4,h5,p,div")].find((el) => {
            if (el.closest("nav[aria-label='Menu categories'], aside")) return false;
            if (el.hasAttribute && el.hasAttribute("data-mp-delivery-sidebar-section")) return false;
            const text = String(el.innerText || "").replace(/\s+/g, " ").trim();
            if (!text || text.length > 90) return false;
            if ((el.innerText || "").split("\n").filter(Boolean).length > 2) return false;
            const plain = text.replace(/\s+\(\d+\)\s*$/, "").trim().toLowerCase();
            return plain === target || text.toLowerCase() === target;
        }) || null;
    }
    function inBand(el, start, end) {
        const y = yOf(el);
        return y >= start - 12 && y < end;
    }

    if (host.includes("magicpin")) {
        const buttons = [...document.querySelectorAll("[data-mp-delivery-sidebar-section], nav[aria-label=\"Menu categories\"] button")];
        const labels = buttons.map((btn) => {
            const attr = btn.getAttribute("data-mp-delivery-sidebar-section") || "";
            const colon = attr.indexOf(":");
            return colon >= 0 ? attr.slice(colon + 1) : String(btn.innerText || "").replace(/\s+\(\d+\)\s*$/, "").trim();
        });
        for (let index = 0; index < buttons.length; index++) {
            const btn = buttons[index];
            const label = labels[index];
            if (isInvalidCategoryName(label)) continue;
            const counted = String(btn.innerText || "").match(/\((\d{1,3})\)\s*$/);
            const cat = addCategory(label, counted && counted[1]) || addCategory("Menu");
            try { btn.scrollIntoView({ block: "center" }); } catch (e) {}
            try { btn.click(); } catch (e) {}
            await sleep(320);
            const heading = contentHeading(cat ? cat.name : label);
            try { heading && heading.scrollIntoView({ block: "start" }); } catch (e) {}
            await sleep(200);
            const nextHeading = labels[index + 1] ? contentHeading(labels[index + 1]) : null;
            const startY = heading ? yOf(heading) : 0;
            const endY = nextHeading ? yOf(nextHeading) : Number.POSITIVE_INFINITY;
            const bounded = Boolean(heading);
            const seenCards = new Set();
            function climbCard(start) {
                let card = start;
                for (let i = 0; i < 12 && card; i++) {
                    const text = card.innerText || "";
                    if (/₹/.test(text) && (/\b(Add|Customise|Order)\b/i.test(text) || (card.hasAttribute && card.hasAttribute("data-catalog-item-id")) || (card.querySelector && card.querySelector("[data-catalog-item-id]"))) && text.length < 1600) return card;
                    card = card.parentElement;
                }
                return null;
            }
            function take(card, food) {
                if (!card || seenCards.has(card)) return;
                if (bounded && !inBand(card, startY, endY)) return;
                seenCards.add(card);
                addItem(cat, parseCard(card, food));
            }
            const cards = document.querySelectorAll("[data-catalog-item-id], [class*=\"ItemCard\" i], [class*=\"delivery-card\" i], [class*=\"product-card\" i]");
            for (const card of cards) {
                if (seenCards.has(card)) continue;
                if (bounded && !inBand(card, startY, endY)) continue;
                const parsed = parseCard(card, null);
                if (parsed) {
                    seenCards.add(card);
                    addItem(cat, parsed);
                }
            }
            const icons = document.querySelectorAll("img[src*=\"veg-icon\"], img[src*=\"non-veg-icon\"], img[src*=\"egg-icon\"]");
            for (const icon of icons) {
                const src = icon.getAttribute("src") || "";
                const food = /non-veg/i.test(src) ? "non-veg" : /egg/i.test(src) ? "egg" : "veg";
                take(climbCard(icon), food);
            }
            const media = document.querySelectorAll("img, source, [style*=\"googleusercontent\"], [data-src], [data-original]");
            for (const node of media) {
                const image = foodImgUrl(node);
                if (!isFoodImage(image)) continue;
                const card = climbCard(node);
                if (!card || seenCards.has(card)) continue;
                if (bounded && !inBand(card, startY, endY)) continue;
                seenCards.add(card);
                const parsed = parseCard(card, null);
                if (parsed) {
                    parsed.image_url = parsed.image_url || image;
                    addItem(cat, parsed);
                }
            }
        }
    }

    if (host.includes("zomato")) {
        const sidebar = [];
        for (const el of document.querySelectorAll("button, p, div, span, a")) {
            const text = String(el.innerText || "").replace(/\s+/g, " ").trim();
            const match = text.match(/^(.{2,60}?)\s+\((\d{1,3})\)$/);
            if (!match || Number(match[2]) < 1 || Number(match[2]) > 200) continue;
            if ((el.innerText || "").split("\n").filter(Boolean).length > 1) continue;
            sidebar.push({ el, name: match[1], count: Number(match[2]) });
        }
        const seenSide = new Set();
        const unique = [];
        for (const row of sidebar) {
            const key = row.name.toLowerCase();
            if (seenSide.has(key)) continue;
            seenSide.add(key);
            unique.push(row);
            addCategory(row.name, row.count);
        }
        async function collectVisible(cat, heading, nextHeading) {
            try { heading && heading.scrollIntoView({ block: "start" }); } catch (e) {}
            await sleep(200);
            const startY = heading ? yOf(heading) : 0;
            const endY = nextHeading ? yOf(nextHeading) : Number.POSITIVE_INFINITY;
            const bounded = Boolean(heading);
            if (!heading && unique.length) return;
            const media = document.querySelectorAll(
                "img[src*=\"dish_photos\"], img[srcset*=\"dish_photos\"], img[data-src*=\"dish_photos\"], img[data-original*=\"dish_photos\"], [style*=\"dish_photos\"], source[srcset*=\"dish_photos\"]"
            );
            for (const node of media) {
                if (bounded && !inBand(node, startY, endY)) continue;
                const image = foodImgUrl(node) || unwrap(node.getAttribute && (node.getAttribute("data-src") || node.getAttribute("data-original")));
                if (!isFoodImage(image)) continue;
                let card = node.parentElement;
                for (let i = 0; i < 10 && card; i++) {
                    const text = card.innerText || "";
                    if (text.split("\n").filter(Boolean).length >= 1 && text.length > 8 && text.length < 900) break;
                    card = card.parentElement;
                }
                const parsed = parseCard(card, null);
                if (!parsed) continue;
                parsed.image_url = parsed.image_url || image;
                addItem(cat, parsed);
            }
        }
        if (!unique.length) await collectVisible(addCategory("Menu"), null, null);
        for (let index = 0; index < unique.slice(0, 40).length; index++) {
            const row = unique[index];
            const cat = addCategory(row.name, row.count);
            try { row.el.scrollIntoView({ block: "center" }); } catch (e) {}
            try { row.el.click(); } catch (e) {}
            await sleep(320);
            const heading = contentHeading(row.name);
            const nextHeading = unique[index + 1] ? contentHeading(unique[index + 1].name) : null;
            if (heading) {
                try { heading.scrollIntoView({ block: "start" }); } catch (e) {}
                await sleep(220);
                try { window.scrollBy(0, 420); } catch (e) {}
                await sleep(220);
                try { window.scrollBy(0, 420); } catch (e) {}
                await sleep(220);
            }
            await collectVisible(cat, heading, nextHeading);
        }
    }

    return {
        dom_menu: categories.filter((item) => item.items.length || item.item_count),
        dom_images: images.slice(0, 400),
    };
}
