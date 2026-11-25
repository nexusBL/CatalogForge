#!/usr/bin/env python
"""Test normalize_image_url fix."""

from backend.catalogue_normalize import normalize_image_url

test_urls = [
    ('https://lh3.googleusercontent.com/1OZbO11ZgN_X3TK7CGaUB0h-AoCyOMmdgMT18Uowujq3v6SqO8vOvZWnnltViJVJtEv_qxaeWFOGKCyXy5GmWvnastXnL9mML4Bf4FE=s1200', True),
    ('https://lh3.googleusercontent.com/test=s120', False),
    ('https://lh3.googleusercontent.com/test=w120', False),
    ('https://lh3.googleusercontent.com/test=w512-rw', False),
]

print("=== NORMALIZE IMAGE URL TEST ===")
for url, should_pass in test_urls:
    display, source, dropped = normalize_image_url(url)
    status = 'PASS' if (display is not None) == should_pass else 'FAIL'
    print(f"{status}: {url[:70]}...")
    print(f"   Display: {display[:50] if display else 'None'}")
    print(f"   Dropped: {dropped}")
    print()
