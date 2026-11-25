from pathlib import Path
import json
import re

html = Path("data/live-scrape-diagnostics/delivery.html").read_text(encoding="utf-8", errors="replace")
i = html.find("Chicken Lemon")
Path("data/live-scrape-diagnostics/snippet.txt").write_text(html[max(0, i - 500) : i + 800], encoding="utf-8")
print("snippet written", i)
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
print("next_data", bool(m), "len", len(m.group(1)) if m else 0)
if m:
    data = json.loads(m.group(1))
    blob = json.dumps(data)
    print("json len", len(blob), "lemonade", "Lemonade" in blob, "Chicken Lemon" in blob)
    Path("data/live-scrape-diagnostics/next-keys.txt").write_text(
        "\n".join(list(data.keys()) if isinstance(data, dict) else ["not-dict"]),
        encoding="utf-8",
    )
