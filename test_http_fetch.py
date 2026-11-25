#!/usr/bin/env python
"""Test HTTP fetch of the image URL."""

import requests

url = 'https://lh3.googleusercontent.com/1OZbO11ZgN_X3TK7CGaUB0h-AoCyOMmdgMT18Uowujq3v6SqO8vOvZWnnltViJVJtEv_qxaeWFOGKCyXy5GmWvnastXnL9mML4Bf4FE=s1200'

print("=== HTTP FETCH TEST ===")
print(f"URL: {url[:70]}...")

try:
    resp = requests.head(url, timeout=10, allow_redirects=True)
    print(f'\nHEAD Status: {resp.status_code}')
    print(f'Content-Type: {resp.headers.get("content-type")}')
    print(f'Final URL: {resp.url[:80]}...')
    
    resp_get = requests.get(url, timeout=10)
    print(f'\nGET Status: {resp_get.status_code}')
    print(f'Content-Length: {len(resp_get.content)}')
    
    if resp_get.content[:4] == b'\xff\xd8\xff':
        print('Content: Valid JPEG image')
    elif resp_get.content[:8] == b'\x89PNG\r\n\x1a\n':
        print('Content: Valid PNG image')
    elif resp_get.content[:3] == b'GIF':
        print('Content: Valid GIF image')
    elif resp_get.content[:4] == b'RIFF':
        print('Content: Valid WEBP image')
    else:
        print(f'Content: Unknown format (first 20 bytes: {resp_get.content[:20]})')
        
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}')
