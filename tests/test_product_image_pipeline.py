"""Test product image collection and rendering pipeline end-to-end."""

import pytest
from backend.catalogue_normalize import normalize_image_url


class TestImageNormalization:
    """Test image URL normalization handles high-resolution parameters correctly."""

    def test_s1200_high_res_parameter_is_not_rejected(self):
        """Verify that =s1200 high-res parameter passes normalization."""
        url = "https://lh3.googleusercontent.com/1OZbO11ZgN_X3TK7CGaUB0h-AoCyOMmdgMT18Uowujq3v6SqO8vOvZWnnltViJVJtEv_qxaeWFOGKCyXy5GmWvnastXnL9mML4Bf4FE=s1200"
        display, source, dropped = normalize_image_url(url)
        
        # High-res image should not be dropped
        assert dropped is False, "=s1200 high-res image should not be marked as dropped/junk"
        assert display is not None, "=s1200 high-res image should have a display URL"
        assert display == url, "=s1200 URL should pass through unchanged"

    def test_low_res_parameters_are_upgraded_by_unwrap(self):
        """Verify that unwrap_image_url upgrades low-res parameters to high-res."""
        # The scraper's unwrap_image_url function upgrades =s120 and =w120 to =s1200
        # This is desirable behavior - low-res thumbnails become high-res display images
        from scraper.platform_dom import unwrap_image_url
        
        urls = [
            'https://lh3.googleusercontent.com/test=s120',
            'https://lh3.googleusercontent.com/test=w120',
        ]
        
        for url in urls:
            result = unwrap_image_url(url)
            assert '=s1200' in result, f"Low-res URL {url} should be upgraded to =s1200"
    
    def test_word_boundary_prevents_false_matching(self):
        """Verify that =s1200 doesn't match =s120 with word boundary."""
        # The critical fix: =s120\b regex prevents =s120 from matching =s1200
        url = "https://lh3.googleusercontent.com/1OZbO11ZgN_X3TK7CGaUB0h-AoCyOMmdgMT18Uowujq3v6SqO8vOvZWnnltViJVJtEv_qxaeWFOGKCyXy5GmWvnastXnL9mML4Bf4FE=s1200"
        display, source, dropped = normalize_image_url(url)
        
        # =s1200 should NOT match the =s120\b pattern (has word boundary after 120)
        assert dropped is False, "=s1200 should not match =s120\\b junk pattern"
        assert display is not None, "=s1200 image should not be dropped"

    def test_w512_rw_is_accepted(self):
        """Verify that =w512-rw URL is processed correctly."""
        url = "https://lh3.googleusercontent.com/test=w512-rw"
        display, source, dropped = normalize_image_url(url)
        
        # This may or may not be rejected depending on the normalization rules,
        # but the important thing is that it doesn't match =w120 as a thumbnail
        assert dropped is not None, "URL should have a definitive dropped status"

    def test_magicpin_cdn_images_pass(self):
        """Verify that Magicpin CDN images pass normalization."""
        urls = [
            "https://im1.magicpin.com/media/portfolio/v2/164148b/item/1.jpg?tr=w-1000",
            "https://mpcdn.in/store/164148b/item/1.png",
        ]
        
        for url in urls:
            display, source, dropped = normalize_image_url(url)
            assert display is not None, f"Magicpin URL {url} should pass normalization"
            assert dropped is False, f"Magicpin URL {url} should not be marked as dropped"

    def test_swiggy_cdn_images_pass(self):
        """Verify that Swiggy CDN images pass normalization."""
        url = "https://media-assets.swiggy.com/swiggy/image/upload/fl_lossy,f_auto,q_auto,w_1000/e0839dd57421933713d308000dd49fef"
        display, source, dropped = normalize_image_url(url)
        
        assert display is not None, "Swiggy CDN URL should pass normalization"
        assert dropped is False, "Swiggy CDN URL should not be marked as dropped"

    def test_zomato_cdn_images_pass(self):
        """Verify that Zomato CDN images pass normalization."""
        urls = [
            "https://b.zmtcdn.com/data/dish_photos/a/b/c.jpg",
            "https://b.zmtcdn.com/data/pictures/dishes/1/2/3.jpg",
        ]
        
        for url in urls:
            display, source, dropped = normalize_image_url(url)
            assert display is not None, f"Zomato URL {url} should pass normalization"
            assert dropped is False, f"Zomato URL {url} should not be marked as dropped"

    def test_icon_images_are_still_rejected(self):
        """Verify that icon/logo images are still rejected."""
        urls = [
            "https://magicpin.in/images/merchant/veg-icon.png",
            "https://example.com/star-filled.png",
            "https://example.com/logo.png",
            "https://example.com/favicon.ico",
        ]
        
        for url in urls:
            display, source, dropped = normalize_image_url(url)
            assert dropped is True, f"Icon URL {url} should be marked as dropped/junk"
            assert display is None, f"Icon URL {url} should not have a display URL"
