#!/usr/bin/env python
"""Debug product image pipeline end-to-end."""

import json
import sys

# Step 1: Find Darjeeling catalogue in backend store
print("=== BACKEND STORE LAYER ===")
from backend.store import list_catalogues, get_catalogue

try:
    catalogues = list_catalogues(user_id="test_user", organization_id="test_org")
    darjeeling_cat = None
    for cat in catalogues:
        if 'darjeeling' in cat.get('name', '').lower():
            darjeeling_cat = cat
            break
    
    if not darjeeling_cat:
        print("ERROR: No Darjeeling catalogue found in store")
        # List available catalogues
        print(f"Available catalogues: {len(catalogues)}")
        for cat in catalogues[:5]:
            print(f"  - {cat.get('name')}")
        sys.exit(1)
    
    cat_id = darjeeling_cat['id']
    print(f"Catalogue ID: {cat_id}")
    print(f"Catalogue Name: {darjeeling_cat['name']}")
    
    # Get full catalogue
    stored = get_catalogue("test_user", cat_id, "test_org")
    if not stored:
        print("ERROR: Catalogue not found")
        sys.exit(1)
    
    payload = stored.get('result', {})
    
except Exception as e:
    print(f"ERROR accessing store: {type(e).__name__}: {e}")
    sys.exit(1)

# Step 2: Extract Plain Maggi from payload
print("\n=== DATABASE STORED VALUES ===")
plain_maggi = None

for cat in payload.get('categories', []):
    for item in cat.get('items', []):
        if 'Plain Maggi' in item.get('name', ''):
            plain_maggi = item
            break
    if plain_maggi:
        break

if not plain_maggi:
    print("ERROR: Plain Maggi not found in catalogue")
    sys.exit(1)

db_image_url = plain_maggi.get('image_url')
print(f"Item Name: {plain_maggi.get('name')}")
print(f"Price: {plain_maggi.get('price')}")
print(f"Image URL: {db_image_url}")
print(f"Source Image URL: {plain_maggi.get('source_image_url')}")

# Step 3: Check normalization logic
print(f"\n=== IMAGE URL NORMALIZATION CHECK ===")
if db_image_url:
    from scraper.platform_dom import unwrap_image_url, is_dish_image
    from scraper.catalogue_normalize import normalize_image_url
    
    unwrapped = unwrap_image_url(db_image_url)
    print(f"After unwrap_image_url: {unwrapped}")
    
    display, source, dropped = normalize_image_url(db_image_url)
    print(f"After normalize_image_url:")
    print(f"  Display: {display}")
    print(f"  Source: {source}")
    print(f"  Dropped: {dropped}")
    
    is_dish = is_dish_image(db_image_url)
    print(f"is_dish_image result: {is_dish}")

# Step 4: Test HTTP fetch
print(f"\n=== HTTP FETCH TEST ===")
if db_image_url:
    try:
        import requests
        print(f"Testing URL: {db_image_url[:80]}...")
        
        resp = requests.head(db_image_url, timeout=10, allow_redirects=True)
        print(f"HEAD Status: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('content-type')}")
        print(f"Content-Length: {resp.headers.get('content-length')}")
        print(f"Final URL: {resp.url[:100] if resp.url else 'N/A'}")
        
        # Try GET for actual content
        resp_get = requests.get(db_image_url, timeout=10)
        print(f"\nGET Status: {resp_get.status_code}")
        print(f"GET Content-Length: {len(resp_get.content)}")
        
        # Check if it's actually an image
        if resp_get.status_code == 200:
            if resp_get.content[:4] == b'\xff\xd8\xff':
                print("✓ Response is a valid JPEG image")
            elif resp_get.content[:8] == b'\x89PNG\r\n\x1a\n':
                print("✓ Response is a valid PNG image")
            else:
                print(f"✗ Response does NOT appear to be image")
                print(f"  First 50 bytes: {resp_get.content[:50]}")
        else:
            print(f"✗ HTTP {resp_get.status_code}")
            
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")

print(f"\n=== CATALOGUE ID ===")
print(f"cat_id={cat_id}")
