import json
import sqlite3

con = sqlite3.connect("data/catalogues.sqlite")
row = con.execute(
    "SELECT id, payload FROM catalogues WHERE id = ?",
    ("50340357-6a54-41f8-a5f8-ffba7805df57",),
).fetchone()
d = json.loads(row[1])
for cat in d.get("categories") or []:
    for item in cat.get("items") or []:
        if "lemon" in (item.get("name") or "").lower():
            print(cat.get("name"), json.dumps(item, ensure_ascii=True)[:800])
