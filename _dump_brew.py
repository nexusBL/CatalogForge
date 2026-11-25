import json
import sqlite3

con = sqlite3.connect("data/catalogues.sqlite")
row = con.execute(
    "SELECT payload FROM catalogues WHERE id = ?",
    ("d22b5c69-dd79-4985-8443-2e8fd247f77a",),
).fetchone()
d = json.loads(row[0])
print("keys", sorted(d.keys()))
print("name", d.get("restaurant_name"), "items", d.get("item_count"), "images", d.get("image_count"))
print("status", d.get("extraction_status"), "platform", d.get("platform"), "type", d.get("catalogue_type"))
print("url", d.get("source_url"))
cats = d.get("categories") or []
print("n_cats", len(cats))
for c in cats[:8]:
    print(" cat", c.get("name"), "item_count", c.get("item_count"), "items", len(c.get("items") or []))
print("restaurant keys", (d.get("restaurant") or {}).keys() if isinstance(d.get("restaurant"), dict) else None)
print("quality", d.get("quality"))
