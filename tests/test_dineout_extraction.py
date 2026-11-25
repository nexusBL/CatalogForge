from scraper.swiggy.dineout import _dineout_image_count, build_dineout_venue, primary_venue_from_url
from scraper.swiggy.models import Restaurant
from scraper.swiggy.parser import parse_swiggy_catalogue
from scraper.swiggy.models import RawSource

DAFFYS_URL = "https://www.swiggy.com/restaurants/bangalore/indiranagar/daffy-s-brewgarden-1242667/dineout"


def test_dineout_venue_maps_restaurant_fields_without_inventing():
    restaurant = Restaurant(
        name="Daffy's Brewgarden",
        rating=4.3,
        rating_count="2K+",
        cuisines=["American", "Continental"],
        price_for_two="₹1800 for two",
        outlet="Indiranagar, Bangalore",
        address="100 Feet Road",
        image_url="https://cdn.example/hero.jpg",
        offers=[{"header": "Flat 20% off", "subHeader": "Pre-booking"}],
        additional_information={"city": "Bangalore", "locality": "Indiranagar", "id": "1242667"},
    )
    venue = build_dineout_venue(restaurant, [], DAFFYS_URL)
    assert venue.venue == "Daffy's Brewgarden"
    assert venue.hero_image == "https://cdn.example/hero.jpg"
    assert venue.offers[0]["title"] == "Flat 20% off"
    assert venue.location["city"] == "Bangalore"
    assert venue.amenities == []
    assert venue.popular_dishes == []
    assert venue.menu_pages == []
    assert venue.restaurant_id == "1242667"


def test_primary_venue_from_dineout_url():
    primary = primary_venue_from_url(DAFFYS_URL)
    assert primary.restaurant_id == "1242667"
    assert primary.name == "Daffy's Brewgarden"


def test_dineout_menu_pages_and_amenities_from_payload():
    restaurant = Restaurant(name="Daffy's Brewgarden")
    payloads = [
        {
            "cards": [
                {
                    "@type": "DineoutMenuCard",
                    "title": "Food",
                    "cloudinaryImageId": "menu/food",
                    "pageCount": 8,
                    "id": "food-menu",
                },
                {"@type": "AmenityInfo", "name": "Valet parking"},
                {"title": "Popular dishes", "items": [{"name": "Honey Almond Pie"}]},
                {"@type": "PhotoGallery", "title": "Ambience", "cloudinaryImageId": "gallery/interior"},
                {"@type": "LocationMap", "title": "Location", "cloudinaryImageId": "maps/daffys"},
            ]
        }
    ]
    venue = build_dineout_venue(restaurant, payloads, DAFFYS_URL)
    assert venue.menu_pages[0]["title"] == "Food"
    assert venue.menu_pages[0]["page_count"] == 8
    assert venue.menu_pages[0]["images"]
    assert "Valet parking" in venue.amenities
    assert "Honey Almond Pie" in venue.popular_dishes
    assert any("interior" in photo for photo in venue.photos)
    assert venue.gallery_images
    assert venue.gallery_images[0].get("category") == "ambience"
    assert venue.location_map_image and "maps/daffys" in venue.location_map_image


def test_recommendation_restaurants_are_not_the_primary_venue():
    restaurant = Restaurant(name="Plan B")
    payloads = [
        {
            "cards": [
                {
                    "info": {
                        "id": "1242667",
                        "name": "Daffy's Brewgarden",
                        "cuisines": ["American", "Continental", "Asian"],
                        "avgRating": 4.4,
                        "totalRatings": 382,
                        "costForTwoMessage": "₹1000 for two",
                        "cloudinaryImageId": "daffys/hero",
                        "locality": "Indiranagar",
                        "city": "Bangalore",
                        "highlights": ["Alcohol served", "Valet parking"],
                        "locationInfo": {
                            "distanceString": "1.2 km",
                            "formattedAddress": "Plot No.48, 100 Feet Road, Indiranagar, Bangalore",
                        },
                        "mediaFiles": [
                            {"type": "IMAGE", "name": "ambience", "url": "daffys/hero"},
                            {"type": "IMAGE", "name": "interior", "url": "daffys/interior"},
                            {"type": "IMAGE", "name": "entrance", "url": "daffys/entrance"},
                            {"type": "IMAGE", "name": "ambience", "url": "daffys/hero?w=800"},
                        ],
                    }
                },
                {
                    "header": {"title": "Recommended options in Nightlife"},
                    "restaurants": [
                        {
                            "info": {
                                "id": "999",
                                "name": "Plan B",
                                "cloudinaryImageId": "planb/hero",
                                "cuisines": ["Nightlife"],
                                "mediaFiles": [
                                    {"type": "IMAGE", "name": "ambience", "url": "planb/gallery-1"},
                                    {"type": "IMAGE", "url": "pangeo/gallery-1"},
                                ],
                            }
                        },
                        {"info": {"id": "998", "name": "Pangeo", "cloudinaryImageId": "pangeo/hero"}},
                    ],
                },
                {
                    "title": "Near Daffy's Brewgarden",
                    "restaurants": [{"info": {"name": "Nearby Cafe", "cloudinaryImageId": "nearby/hero"}}],
                },
                {
                    "title": "More American restaurants",
                    "restaurants": [{"info": {"name": "Other American", "cloudinaryImageId": "other/hero"}}],
                },
                {
                    "title": "Brands near you",
                    "restaurants": [{"info": {"name": "A Brand", "cloudinaryImageId": "brand/hero"}}],
                },
                {"title": "Popular dishes", "items": [{"name": "Plan B"}, {"name": "Honey Almond Pie"}]},
            ]
        }
    ]
    venue = build_dineout_venue(restaurant, payloads, DAFFYS_URL)
    assert venue.venue == "Daffy's Brewgarden"
    assert venue.restaurant_id == "1242667"
    assert venue.hero_image and "daffys/hero" in venue.hero_image
    assert "planb" not in (venue.hero_image or "")
    assert "pangeo" not in (venue.hero_image or "")
    assert venue.venue != "Plan B"
    assert "Plan B" not in venue.popular_dishes
    assert "Honey Almond Pie" in venue.popular_dishes
    assert not any("planb" in (photo or "") for photo in venue.photos)
    assert not any("pangeo" in (photo or "") for photo in venue.photos)
    assert not any("nearby" in (photo or "") for photo in venue.photos)
    offer_titles = [offer["title"] for offer in venue.offers]
    assert "Recommended options in Nightlife" not in offer_titles
    assert len(venue.gallery_images) >= 3
    gallery_blob = " ".join(item["url"] for item in venue.gallery_images)
    assert "daffys/interior" in gallery_blob
    assert "daffys/entrance" in gallery_blob
    assert "planb/gallery" not in gallery_blob
    assert "pangeo/gallery" not in gallery_blob
    assert len([item for item in venue.gallery_images if "daffys/hero" in item["url"]]) == 1
    assert "Alcohol served" in venue.amenities
    assert venue.location.get("address") == "Plot No.48, 100 Feet Road, Indiranagar, Bangalore"
    assert venue.location.get("distance") == "1.2 km"
    assert "Near Daffy's Brewgarden" not in offer_titles
    assert "More American restaurants" not in offer_titles
    assert "Brands near you" not in offer_titles
    assert "Photos" not in offer_titles
    assert "Plan B" not in offer_titles
    assert "Pangeo" not in offer_titles


def test_recommendation_widgets_are_not_stored_as_offers():
    restaurant = Restaurant(
        name="Daffy's Brewgarden",
        offers=[
            {"header": "Recommended options in Nightlife"},
            {"title": "Near Daffy's Brewgarden"},
            {"title": "More American restaurants"},
            {"title": "Photos"},
            {"header": "Free Beer", "subHeader": "On pre-booking"},
            {"header": "10% cashback", "couponCode": "SWIGGYIT"},
        ],
    )
    payloads = [
        {
            "cards": [
                {"header": {"title": "Recommended options in Nightlife"}, "restaurants": [{"info": {"name": "Plan B"}}]},
                {"title": "Photos", "cloudinaryImageId": "gallery/interior"},
                {"@type": "type.googleapis.com/swiggy.presentation.dineout.OfferCard", "header": "Flat 20% off"},
            ]
        }
    ]
    venue = build_dineout_venue(restaurant, payloads, DAFFYS_URL)
    titles = [offer["title"] for offer in venue.offers]
    assert "Recommended options in Nightlife" not in titles
    assert "Near Daffy's Brewgarden" not in titles
    assert "More American restaurants" not in titles
    assert "Photos" not in titles
    assert "Free Beer" in titles
    assert "10% cashback" in titles
    assert "Flat 20% off" in titles
    assert "Offers for you" not in titles
    assert "Pre-booking offers" not in titles


def test_menu_pages_group_by_section_title():
    restaurant = Restaurant(name="Daffy's Brewgarden")
    payloads = [
        {
            "cards": [
                {"@type": "DineoutMenuCard", "title": "Food", "cloudinaryImageId": "menu/food-1", "id": "food-1"},
                {"@type": "DineoutMenuCard", "title": "Food", "cloudinaryImageId": "menu/food-2", "id": "food-2"},
                {"@type": "DineoutMenuCard", "title": "Bar", "cloudinaryImageId": "menu/bar", "id": "bar-1"},
            ]
        }
    ]
    venue = build_dineout_venue(restaurant, payloads, DAFFYS_URL)
    titles = [page["title"] for page in venue.menu_pages]
    assert titles.count("Food") == 1
    assert titles.count("Bar") == 1
    food = next(page for page in venue.menu_pages if page["title"] == "Food")
    assert len(food["images"]) == 2
    assert food["page_count"] == 2


def test_ambience_hero_and_menu_images_are_classified():
    restaurant = Restaurant(name="Plan B", image_url="https://cdn.example/planb.jpg")
    html = """
    <section><h2>Recommended options in Nightlife</h2>
      <img src="https://dineout-media-assets.swiggy.com/planb.jpg" alt="Plan B">
    </section>
    <img class="sc-hLQRIN eFunMy" src="https://dineout-media-assets.swiggy.com/daffys/ambience.jpg" width="100%" height="100%" alt="Ambience">
    <img src="https://dineout-media-assets.swiggy.com/daffys/interior.jpg" alt="Interior">
    <img src="https://dineout-media-assets.swiggy.com/daffys/breakfast.jpg" alt="Breakfast">
    <img src="https://dineout-media-assets.swiggy.com/daffys/food.jpg" alt="Food">
    <img src="https://dineout-media-assets.swiggy.com/daffys/bar.jpg" alt="Bar">
    """
    venue = build_dineout_venue(
        restaurant,
        [{"info": {"id": "1242667", "name": "Daffy's Brewgarden", "locality": "Indiranagar"}}],
        DAFFYS_URL,
        html=html,
        dom_images=[
            {
                "url": "https://dineout-media-assets.swiggy.com/planb-card.jpg",
                "alt": "Plan B",
                "section": "Recommended options in Nightlife",
            },
            {
                "url": "https://dineout-media-assets.swiggy.com/maps/daffys.png",
                "alt": "Location",
                "section": "Location",
            },
        ],
    )
    assert venue.venue == "Daffy's Brewgarden"
    assert venue.hero_image and "ambience" in venue.hero_image
    assert "planb" not in (venue.hero_image or "")
    assert any("interior" in item["url"] for item in venue.gallery_images)
    assert not any("breakfast" in item["url"] for item in venue.gallery_images)
    assert {page["title"] for page in venue.menu_pages} >= {"Breakfast", "Food", "Bar"}
    assert venue.location_map_image and "maps/daffys" in venue.location_map_image
    assert not any("planb" in (item["url"] or "") for item in venue.gallery_images)


def test_close_icon_is_not_a_venue_photo():
    restaurant = Restaurant(name="Daffy's Brewgarden")
    html = """
    <img class="sc-hLQRIN eFunMy" src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/fl_lossy,f_auto,q_auto/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/c62bce32-a7b8-46d8-800b-7ee59ba84114_image2be7594d5b34446ac9171f7bbbf270eeb.JPG" alt="Ambience">
    <img src="https://media-assets.swiggy.com/swiggy/image/upload/fl_lossy,f_auto,q_auto/seo%20web/cross.png">
    """
    venue = build_dineout_venue(
        restaurant,
        [{"info": {"id": "1242667", "name": "Daffy's Brewgarden"}}],
        DAFFYS_URL,
        html=html,
    )
    blob = " ".join(item["url"] for item in venue.gallery_images)
    assert "image2be7594d5b34446ac9171f7bbbf270eeb" in blob
    assert "cross.png" not in blob
    assert "seo" not in blob.lower() or "cross" not in blob.lower()


def test_offer_images_and_popular_dishes_are_classified_from_page():
    restaurant = Restaurant(name="Daffy's Brewgarden")
    html = """
    <h2>Offers for you</h2>
    <img src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/dineout/OneExclusive.png" alt="">
    <p>Free Beer</p>
    <img src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/dineout/loyalty/nba_rupees.png" alt="">
    <p>10% cashback</p>
    <img src="https://media-assets.swiggy.com/swiggy/image/upload/portal/static-assets/icons/dineout/plus_icon_black_background.png">
    <h2>Popular dishes</h2>
    Daffy's Bar Bite
    Honey Almond Pie
    <h2>Cuisines</h2>
    <h2>Photos</h2>
    <img class="eFunMy" src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/venue.JPG" alt="Ambience">
    """
    payloads = [
        {
            "info": {
                "id": "1242667",
                "name": "Daffy's Brewgarden",
                "offers": [
                    {"header": "Free Beer", "subHeader": "Available on Mon-Sun with booking fee: ₹25"},
                    {"header": "10% cashback", "subHeader": "On every bill payment"},
                ],
            }
        }
    ]
    venue = build_dineout_venue(restaurant, payloads, DAFFYS_URL, html=html)
    assert venue.offers[0]["title"] == "Free Beer"
    assert "OneExclusive" in (venue.offers[0].get("image") or "")
    assert "nba_rupees" in (venue.offers[1].get("image") or "")
    gallery = " ".join(item["url"] for item in venue.gallery_images)
    assert "OneExclusive" not in gallery
    assert "nba_rupees" not in gallery
    assert "plus_icon" not in gallery
    assert "popular_dishes" not in gallery
    assert "Honey Almond Pie" in venue.popular_dishes
    assert "Daffy's Bar Bite" in venue.popular_dishes
    assert venue.hero_image and "venue.JPG" in venue.hero_image


def test_photo_widget_view_photo_grid_is_venue_gallery():
    restaurant = Restaurant(name="Daffy's Brewgarden")
    html = """
    <div data-testid="rdp_photos_widget" id="photos" class="PhotoWidget__Container-sc-g5qo0l-0">
    <div class="PhotoWidget__DesktopPhotoGridWrapper-sc-g5qo0l-1">
    <div class="PhotoWidget__DesktopPhotoGrid-sc-g5qo0l-2">
      <div aria-label="View photo 1" class="PhotoWidget__DesktopPhotoGridItem-sc-g5qo0l-3">
        <img class="sc-hLQRIN eFunMy" alt="Photos" src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/photo-one.JPG">
      </div>
      <div aria-label="View photo 2" class="PhotoWidget__DesktopPhotoGridItem-sc-g5qo0l-3">
        <img class="sc-hLQRIN eFunMy" alt="Photos" src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/photo-two.JPG">
      </div>
      <div aria-label="View photo 6" class="PhotoWidget__DesktopPhotoGridItem-sc-g5qo0l-3">
        <img class="sc-hLQRIN eFunMy" alt="Photos" src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/photo-six.JPG">
      </div>
    </div>
    </div>
    </div>
    <button type="button" class="ImageCarousel__CarouselButton-sc-nygw0y-3 kZNzIT carousel-button" aria-label="Next slide"></button>
    <button type="button">Show all images</button>
    <button type="button">1/31</button>
    <img class="ImageCarousel__ImageContainer-sc-nygw0y-5" alt="Slide 7" src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/photo-seven.JPG">
    <img class="sc-hLQRIN eFunMy MenuSectionWidget__MenuCardImage-sc-z8vlor-13" alt="Food" src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2026/6/28/FoodMenuDaffys.JPG">
    <img class="ImageCarousel__ImageContainer" src="https://media-assets.swiggy.com/swiggy/image/upload/seo%20web/iconLeft.png" alt="">
    <img class="ImageCarousel__ImageContainer" src="https://media-assets.swiggy.com/swiggy/image/upload/seo%20web/iconRight.png" alt="">
    <img class="ImageCarousel__ImageContainer" src="https://media-assets.swiggy.com/swiggy/image/upload/fl_lossy,f_auto,q_auto/seo%20web/cross.png" alt="">
    """
    venue = build_dineout_venue(
        restaurant,
        [{"info": {"id": "1242667", "name": "Daffy's Brewgarden"}}],
        DAFFYS_URL,
        html=html,
        dom_images=[
            {
                "url": "https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/photo-one.JPG",
                "alt": "Photos",
                "section": "Photos",
                "className": "sc-hLQRIN eFunMy",
            }
        ],
    )
    blob = " ".join(item["url"] for item in venue.gallery_images)
    assert "photo-one" in blob
    assert "photo-two" in blob
    assert "photo-six" in blob
    assert "photo-seven" in blob
    assert "FoodMenuDaffys" not in blob
    assert "iconLeft" not in blob
    assert "iconRight" not in blob
    assert "cross.png" not in blob
    assert any("FoodMenuDaffys" in (page.get("image") or "") for page in venue.menu_pages)
    assert _dineout_image_count(venue) >= 4


def test_image_carousel_slide_images_are_venue_photos():
    restaurant = Restaurant(name="Daffy's Brewgarden")
    html = """
    <img class="sc-hLQRIN kiycay ImageCarousel__ImageContainer-sc-nygw0y-5 gCqsPK"
         src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/fl_lossy,f_auto,q_auto/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/88-2b13-48c8-825e-2b49aba2a652_image24a389.JPG"
         width="1172px" height="793px" alt="Slide 6">
    <img class="ImageCarousel__ImageContainer-sc-nygw0y-5"
         src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/slide-two.JPG"
         alt="Slide 2">
    <img src="https://dineout-media-assets.swiggy.com/swiggy/image/upload/dineout/OneExclusive.png" alt="">
    """
    venue = build_dineout_venue(
        restaurant,
        [{"info": {"id": "1242667", "name": "Daffy's Brewgarden"}}],
        DAFFYS_URL,
        html=html,
        dom_images=[
            {
                "url": "https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/88-2b13-48c8-825e-2b49aba2a652_image24a389.JPG",
                "alt": "Slide 6",
                "section": "Photos",
                "className": "sc-hLQRIN kiycay ImageCarousel__ImageContainer-sc-nygw0y-5 gCqsPK",
            }
        ],
    )
    blob = " ".join(item["url"] for item in venue.gallery_images)
    assert "image24a389" in blob
    assert "slide-two" in blob
    assert "OneExclusive" not in blob
    assert not any("image24a389" in (page.get("image") or "") for page in venue.menu_pages)


def test_location_map_image_and_maps_url_from_directions():
    restaurant = Restaurant(name="Daffy's Brewgarden")
    payloads = [
        {
            "info": {
                "id": "1242667",
                "name": "Daffy's Brewgarden",
                "directionUrl": "https://www.google.com/maps/dir/?api=1&destination=12.9767657,77.6412512",
            }
        }
    ]
    venue = build_dineout_venue(restaurant, payloads, DAFFYS_URL)
    assert venue.directions_url and "12.9767657" in venue.directions_url
    assert venue.location.get("maps_url") and "12.9767657" in venue.location["maps_url"]
    assert venue.location_map_image and "staticmap" in venue.location_map_image
    assert "12.9767657" in venue.location_map_image


def test_missing_gallery_and_location_fields_are_omitted():
    venue = build_dineout_venue(Restaurant(name="Daffy's Brewgarden"), [], DAFFYS_URL)
    assert venue.gallery_images == []
    assert not venue.location_map_image
    assert "Not available" not in str(venue.location)


def test_implausible_last_mile_distance_is_omitted():
    restaurant = Restaurant(name="Daffy's Brewgarden")
    payloads = [
        {
            "info": {
                "id": "1242667",
                "name": "Daffy's Brewgarden",
                "lastMileTravelString": "349.5 km",
                "sla": {"lastMileTravelString": "349.5 km"},
                "locationInfo": {
                    "distanceString": "349.5 km",
                    "latitude": "12.9767657",
                    "longitude": "77.6412512",
                },
                "directionUrl": "https://www.google.com/maps/dir/?api=1&origin=12.91870,74.85980&destination=12.9767657,77.6412512",
            }
        }
    ]
    html = """
    <section>Location 349.5 km • Plot No.48, Ground Floor, 100 Feet Road, Defence Colony, Indiranagar, Bangalore, Karnataka</section>
    """
    venue = build_dineout_venue(restaurant, payloads, DAFFYS_URL, html=html)
    assert venue.location.get("distance") is None
    assert "349.5" not in str(venue.location.get("distance") or "")
    assert "Plot No.48" in (venue.location.get("address") or "")
    assert venue.location.get("maps_url") and "12.9767657" in venue.location["maps_url"]
    assert venue.directions_url and "destination=12.9767657" in venue.directions_url
    assert "origin=" not in (venue.directions_url or "")
    assert venue.location_map_image and "staticmap" in venue.location_map_image


def test_local_venue_distance_is_kept():
    restaurant = Restaurant(name="Daffy's Brewgarden")
    payloads = [
        {
            "info": {
                "id": "1242667",
                "name": "Daffy's Brewgarden",
                "locationInfo": {"distanceString": "0.2 km"},
            }
        }
    ]
    venue = build_dineout_venue(restaurant, payloads, DAFFYS_URL)
    assert venue.location.get("distance") == "0.2 km"


def test_html_gallery_excludes_recommendation_image_files():
    restaurant = Restaurant(name="Daffy's Brewgarden")
    html = """
    <img src="https://media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/1/1/daffys-one.JPG">
    <img src="https://media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/1/1/daffys-two.JPG">
    <img src="https://media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/1/1/planb-steal.JPG">
    """
    payloads = [
        {
            "info": {
                "id": "999",
                "name": "Plan B",
                "mediaFiles": [{"type": "IMAGE", "url": "DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/1/1/planb-steal.JPG"}],
            }
        },
        {"info": {"id": "1242667", "name": "Daffy's Brewgarden"}},
    ]
    venue = build_dineout_venue(restaurant, payloads, DAFFYS_URL, html=html)
    blob = " ".join(item["url"] for item in venue.gallery_images)
    assert "daffys-one" in blob
    assert "daffys-two" in blob
    assert "planb-steal" not in blob
    restaurant = Restaurant(name="Daffy's Brewgarden")
    venue = build_dineout_venue(restaurant, [], DAFFYS_URL)
    assert venue.offers == []
    assert venue.amenities == []
    assert venue.popular_dishes == []
    assert venue.hero_image is None or venue.hero_image


def test_parser_keeps_restaurant_and_dineout_and_both_types():
    dineout_raw = RawSource(
        source_url=DAFFYS_URL,
        html='<img src="https://dineout-media-assets.swiggy.com/x/ambience.jpg" alt="Ambience">',
        api_payloads=[{"info": {"id": "1242667", "name": "Daffy's Brewgarden", "avgRating": 4.4}}],
    )
    dineout = parse_swiggy_catalogue(dineout_raw)
    assert dineout.dineout
    assert dineout.dineout.restaurant_id == "1242667"
    assert dineout.dineout.hero_image and "ambience" in dineout.dineout.hero_image

    restaurant_raw = RawSource(
        source_url="https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
        api_payloads=[
            {
                "data": {
                    "cards": [
                        {
                            "card": {
                                "card": {
                                    "@type": "type.googleapis.com/swiggy.presentation.food.v2.Restaurant",
                                    "info": {"name": "Harbor Spice House", "cuisines": ["Coastal"]},
                                }
                            }
                        }
                    ]
                }
            }
        ],
    )
    restaurant_catalogue = parse_swiggy_catalogue(restaurant_raw)
    assert restaurant_catalogue.restaurant.name == "Harbor Spice House"


def test_parser_attaches_dineout_on_ok_catalogue():
    raw = RawSource(
        source_url="https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
        api_payloads=[
            {
                "data": {
                    "cards": [
                        {
                            "card": {
                                "card": {
                                    "@type": "type.googleapis.com/swiggy.presentation.food.v2.Restaurant",
                                    "info": {"name": "Harbor Spice House", "cuisines": ["Coastal"]},
                                }
                            }
                        }
                    ]
                }
            }
        ],
    )
    catalogue = parse_swiggy_catalogue(raw)
    if catalogue.extraction_status == "ok" and catalogue.dineout:
        assert catalogue.dineout.venue == "Harbor Spice House"


def test_dineout_videos_are_separate_from_photos():
    html = """
    <video src="https://cdn.example/venue-ambience.mp4"></video>
    <source src="https://cdn.example/clip.webm" type="video/webm">
    <img src="https://cdn.example/menu-scan.jpg" alt="menu">
    """
    venue = build_dineout_venue(Restaurant(name="Daffy's Brewgarden"), [], DAFFYS_URL, html=html)
    urls = [item["source_url"] for item in venue.videos]
    assert "https://cdn.example/venue-ambience.mp4" in urls
    assert "https://cdn.example/clip.webm" in urls
    assert all("menu-scan" not in (item.get("url") or "") for item in venue.gallery_images)

