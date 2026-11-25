#!/usr/bin/env python
"""Debug database access and find Darjeeling catalogue."""

import sqlite3
import json
from pathlib import Path

db_path = Path("data/catalogues.sqlite")
if not db_path.exists():
    print(f"Database not found at {db_path}")
    print(f"Current directory: {Path.cwd()}")
    exit(1)

conn = sqlite3.connect(str(db_path))
c = conn.cursor()

# List all tables
print("=== DATABASE TABLES ===")
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
for row in c.fetchall():
    print(f"  {row[0]}")

# Check catalogues table schema
print("\n=== CATALOGUES TABLE SCHEMA ===")
c.execute("PRAGMA table_info(catalogues)")
for row in c.fetchall():
    print(f"  {row}")

# Check catalogues table
print("\n=== CATALOGUES TABLE ===")
c.execute("SELECT COUNT(*) FROM catalogues")
count = c.fetchone()[0]
print(f"Total catalogues: {count}")

if count > 0:
    print("\nFirst 5 catalogues:")
    c.execute("SELECT id, user_id, organization_id, extraction_status FROM catalogues LIMIT 5")
    for row in c.fetchall():
        cat_id, user_id, org_id, status = row
        print(f"  ID: {cat_id[:8]}...")
        print(f"    User: {user_id}")
        print(f"    Org: {org_id}")
        print(f"    Status: {status}")

# Search for Darjeeling
print("\n=== SEARCHING FOR DARJEELING ===")
c.execute("SELECT id, user_id, organization_id FROM catalogues")
found_count = 0
for row in c.fetchall():
    cat_id, user_id, org_id = row
    c.execute("SELECT payload FROM catalogues WHERE id = ?", (cat_id,))
    payload_row = c.fetchone()
    if payload_row:
        try:
            payload = json.loads(payload_row[0])
            name = payload.get('restaurant', {}).get('name') or payload.get('dineout', {}).get('venue') or ""
            if 'darjeeling' in name.lower() and 'momos' in name.lower():
                found_count += 1
                print(f"\nFOUND #{found_count}: {name}")
                print(f"  Catalogue ID: {cat_id}")
                print(f"  User ID: {user_id}")
                print(f"  Org ID: {org_id}")
                
                # Extract Plain Maggi
                for cat in payload.get('categories', []):
                    for item in cat.get('items', []):
                        if 'Plain Maggi' in item.get('name', ''):
                            print(f"\n  === PLAIN MAGGI ===")
                            print(f"  Item: {item.get('name')}")
                            print(f"  Price: {item.get('price')}")
                            print(f"  Image URL: {item.get('image_url')}")
                            print(f"  Source Image URL: {item.get('source_image_url')}")
        except Exception as e:
            print(f"Error parsing: {e}")

if found_count == 0:
    print("No Darjeeling catalogue found. Available catalogues:")
    c.execute("SELECT id, user_id FROM catalogues LIMIT 5")
    for row in c.fetchall():
        cat_id, user_id = row
        c.execute("SELECT payload FROM catalogues WHERE id = ?", (cat_id,))
        payload_row = c.fetchone()
        if payload_row:
            try:
                payload = json.loads(payload_row[0])
                name = payload.get('restaurant', {}).get('name') or payload.get('dineout', {}).get('venue') or ""
                print(f"  - {name} ({cat_id[:8]}...)")
            except:
                pass

conn.close()
