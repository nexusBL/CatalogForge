import json
import sqlite3

con = sqlite3.connect("data/catalogues.sqlite")
con.row_factory = sqlite3.Row
row = con.execute("SELECT * FROM catalogues WHERE id = ?", ("d22b5c69-dd79-4985-8443-2e8fd247f77a",)).fetchone()
print(row.keys() if row else None)
if row:
    print("user", row["user_id"] if "user_id" in row.keys() else None)
    print("org", row["organization_id"] if "organization_id" in row.keys() else None)
    d = json.loads(row["payload"])
    print("org payload", d.get("organization_id"))
