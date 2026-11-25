from pathlib import Path

from scraper.swiggy.assets import materialize_catalogue_images


def test_materialize_downloads_and_rewrites_image_fields(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_DOWNLOAD_IMAGES", "1")
    monkeypatch.setenv("CATALOGFORGE_ASSETS_DIR", str(tmp_path))
    payload = {
        "dineout": {
            "hero_image": "https://cdn.example/hero.jpg",
            "offers": [{"title": "Free Beer", "image": "https://cdn.example/offer.png"}],
            "gallery_images": [{"url": "https://cdn.example/photo.jpg", "category": "ambience"}],
            "menu_pages": [{"title": "Food", "image": "https://cdn.example/menu.jpg", "images": ["https://cdn.example/menu.jpg"]}],
            "location": {"maps_url": "https://www.google.com/maps?q=1,2"},
            "source_url": "https://www.swiggy.com/restaurants/x/dineout",
        },
        "categories": [
            {
                "name": "Recommended",
                "items": [{"name": "Paneer Makhni Biryani", "image_url": "https://lh3.googleusercontent.com/paneer=w512-rw"}],
            }
        ],
    }

    def fetch(url: str) -> bytes | None:
        return b"fake-bytes-" + url.encode()

    materialize_catalogue_images(payload, "cat-1", fetch=fetch)
    venue = payload["dineout"]
    assert venue["hero_image"].startswith("/catalogue-assets/cat-1/")
    assert (tmp_path / "cat-1" / Path(venue["hero_image"]).name).exists()
    assert venue["offers"][0]["image"].startswith("/catalogue-assets/cat-1/")
    assert venue["offers"][0]["source_image_url"] == "https://cdn.example/offer.png"
    assert venue["gallery_images"][0]["url"].startswith("/catalogue-assets/cat-1/")
    assert venue["gallery_images"][0]["source_url"] == "https://cdn.example/photo.jpg"
    assert venue["menu_pages"][0]["image"].startswith("/catalogue-assets/cat-1/")
    assert venue["location"]["maps_url"] == "https://www.google.com/maps?q=1,2"
    assert venue["source_url"].startswith("https://www.swiggy.com")
    item = payload["categories"][0]["items"][0]
    assert item["image_url"].startswith("/catalogue-assets/cat-1/")
    assert item["source_image_url"] == "https://lh3.googleusercontent.com/paneer=w512-rw"


def test_failed_download_keeps_source_url(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_DOWNLOAD_IMAGES", "1")
    monkeypatch.setenv("CATALOGFORGE_ASSETS_DIR", str(tmp_path))
    payload = {"dineout": {"hero_image": "https://cdn.example/missing.jpg", "offers": [{"title": "Keep me"}]}}
    materialize_catalogue_images(payload, "cat-2", fetch=lambda _url: None)
    assert payload["dineout"]["hero_image"] == "https://cdn.example/missing.jpg"
    assert payload["dineout"]["offers"][0]["title"] == "Keep me"
