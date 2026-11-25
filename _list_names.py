from pathlib import Path
import html as html_lib
import re

raw = Path("data/live-scrape-diagnostics/delivery.html").read_text(encoding="utf-8", errors="replace")
names = [
    html_lib.unescape(name)
    for name in re.findall(
        r'data-catalog-item-id="\d+"[\s\S]{0,1500}?<h4[^>]*>[\s\S]*?>([^<]{2,90})</a>',
        raw,
    )
]
Path("data/live-scrape-diagnostics/item-names.txt").write_text("\n".join(names), encoding="utf-8")
print("count", len(names))
print("lemon", [n for n in names if "lemon" in n.lower()])
print("paneer", [n for n in names if "paneer" in n.lower()][:10])
# category markers near first item
i = raw.find("data-catalog-item-id")
print(raw[max(0, i - 800) : i + 200].replace("\n", " ")[:900])
