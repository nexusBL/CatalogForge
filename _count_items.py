from pathlib import Path
import re

html = Path("data/live-scrape-diagnostics/delivery.html").read_text(encoding="utf-8", errors="replace")
ids = re.findall(r'data-catalog-item-id="(\d+)"', html)
print("item ids", len(ids), "unique", len(set(ids)))
names = re.findall(r'data-catalog-item-id="\d+"[\s\S]{0,1200}?<h4[^>]*>[\s\S]*?>([^<]{3,80})</a>', html)
print("names", len(names), names[:15])
prices = re.findall(r"₹(?:<!-- -->)?(\d+)", html)
print("rupees", len(prices), prices[:10])
heads = re.findall(r"data-mp-delivery-sidebar-section=\"\d+:([^\"]+)\"", html)
print("sidebar", len(heads), heads[:8])
