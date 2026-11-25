from scraper.gallery_walk import (
    is_owned_gallery_context,
    photo_plus_label,
    should_traverse_gallery,
)
from scraper.magicpin.parser import parse_magicpin_catalogue
from scraper.swiggy.models import RawSource
from scraper.zomato.parser import parse_zomato_catalogue


def test_gallery_traversal_targets_venue_pages_only():
    assert should_traverse_gallery("https://www.zomato.com/city/venue")
    assert should_traverse_gallery("https://www.zomato.com/city/venue/photos")
    assert not should_traverse_gallery("https://www.zomato.com/city/venue/order")
    assert should_traverse_gallery("https://magicpin.in/City/Area/Restaurant/Name/store/abc")
    assert not should_traverse_gallery("https://magicpin.in/City/Area/Restaurant/Name/store/abc/delivery")
    assert not should_traverse_gallery("https://www.swiggy.com/city/x/y/dineout")
    assert photo_plus_label("+76 Photos")
    assert photo_plus_label("+300 Photos")
    assert not photo_plus_label("Photos nearby")
    assert is_owned_gallery_context("Ambience", "Venue gallery")
    assert not is_owned_gallery_context("Plan B", "Recommended restaurants nearby")


def test_zomato_and_magicpin_videos_stay_out_of_photos():
    zomato = parse_zomato_catalogue(
        RawSource(
            source_url="https://www.zomato.com/sample/venue",
            access_status="ok",
            html="""
            <h1>Sample Venue</h1>
            <video src="https://cdn.example/venue.mp4" poster="https://cdn.example/thumb.jpg"></video>
            <img src="https://b.zmtcdn.com/data/pictures/1/123/ambience.jpg" alt="Ambience">
            <img src="https://b.zmtcdn.com/data/pictures/9/999/similar.jpg" alt="Similar restaurants nearby">
            """,
        )
    )
    assert zomato.dineout
    urls = [item["source_url"] for item in zomato.dineout.videos]
    assert "https://cdn.example/venue.mp4" in urls
    gallery = " ".join(item["url"] for item in zomato.dineout.gallery_images)
    assert "ambience.jpg" in gallery
    assert "venue.mp4" not in gallery
    magicpin = parse_magicpin_catalogue(
        RawSource(
            source_url="https://magicpin.in/City/Area/Restaurant/Name/store/abc",
            access_status="ok",
            html="""
            <h1>Sample Store</h1>
            <a>+20 Photos</a>
            <video src="https://cdn.magicpin.in/videos/walkthrough.mp4"></video>
            <img alt="Recommended restaurants" src="https://lh3.googleusercontent.com/nearby=w800">
            """,
        )
    )
    assert magicpin.dineout
    assert any("walkthrough.mp4" in item["source_url"] for item in magicpin.dineout.videos)
    assert all("walkthrough.mp4" not in (item.get("url") or "") for item in magicpin.dineout.gallery_images)
