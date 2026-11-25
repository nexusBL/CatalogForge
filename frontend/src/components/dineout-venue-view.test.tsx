import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { OverviewCatalogueCard } from "@/components/overview-catalogue-card";
import { DineoutVenueView } from "@/components/dineout-venue-view";
import { CatalogueView } from "@/components/catalogue-view";
import type { CatalogCreateResponse, StoredCatalogue } from "@/lib/catalog-types";

const dineout: CatalogCreateResponse = {
  extraction_status: "ok",
  restaurant_name: "Daffy's Brewgarden",
  fssai_number: "",
  source_url: "https://www.swiggy.com/restaurants/daffys/dineout",
  catalogue_type: "dineout",
  dineout: {
    venue: "Daffy's Brewgarden",
    hero_image: "https://cdn.example/hero.jpg",
    rating: 4.3,
    rating_count: "2K+",
    cuisines: ["American", "Continental"],
    price_for_two: "₹1800 for two",
    offers: [{ title: "Flat 20% off", description: "Pre-booking", image: "https://cdn.example/offer.png" }],
    menu_pages: [{ title: "Food", image: "https://cdn.example/menu.jpg", page_count: 8, identity: "food" }],
    popular_dishes: ["Honey Almond Pie"],
    photos: ["https://cdn.example/photo.jpg", "https://cdn.example/photo-2.jpg"],
    gallery_images: [
      { url: "https://cdn.example/photo.jpg", category: "ambience" },
      { url: "https://cdn.example/photo-2.jpg", category: "interior" },
    ],
    amenities: ["Valet parking", "Alcohol served"],
    location: {
      locality: "Indiranagar, Bangalore",
      address: "100 Feet Road",
      maps_url: "https://www.google.com/maps?q=12.97,77.64",
      map_image: "https://cdn.example/map.jpg",
    },
    location_map_image: "https://cdn.example/map.jpg",
    directions_url: "https://maps.google.com/?q=daffys",
    actions: { directions: "https://maps.google.com/?q=daffys", call: "08012345678" },
  },
};

describe("dineout presentation", () => {
  it("renders extracted dineout sections and hides missing ones", () => {
    const html = renderToStaticMarkup(<DineoutVenueView venue={dineout.dineout!} />);
    expect(html).toContain("Brewgarden");
    expect(html).toContain("Indiranagar, Bangalore");
    expect(html).toContain("Offers");
    expect(html).toContain("Flat 20% off");
    expect(html).toContain("cdn.example/offer.png");
    expect(html).toContain("w-[280px]");
    expect(html).toContain("data-flash-offer");
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain("Menu");
    expect(html).toContain("8 pages");
    expect(html).toContain("Popular dishes");
    expect(html).toContain("Honey Almond Pie");
    expect(html).toContain("American");
    expect(html).toContain("Photos");
    expect(html).toContain("View all images");
    expect(html).toContain("Open in Maps");
    expect(html).toContain("Valet parking");
    expect(html).toContain("Directions");
    expect(html).toContain("Call");
    expect(html).toContain("h-[280px]");
    expect(html).toContain("cdn.example/photo-2.jpg");
    expect(html).not.toContain("349.5 km");
    expect(html).not.toContain("Delete Catalogue");
    expect(html).not.toContain("Not available");
    expect(html).not.toContain("FSSAI");
    expect(html).not.toContain(">Videos<");
    expect(html).not.toContain("Recommended options in Nightlife");
    expect(html).not.toContain("Plan B");
  });

  it("renders videos only when the venue has video sources", () => {
    const html = renderToStaticMarkup(
      <DineoutVenueView
        venue={{
          ...dineout.dineout!,
          videos: [{ source_url: "https://cdn.example/venue.mp4", title: "Walkthrough" }],
        }}
      />,
    );
    expect(html).toContain("Videos");
    expect(html).toContain("https://cdn.example/venue.mp4");
    expect(html).toContain("Walkthrough");
  });

  it("hides discovery titles that were incorrectly stored as offers", () => {
    const html = renderToStaticMarkup(
      <DineoutVenueView
        venue={{
          venue: "Daffy's Brewgarden",
          location: { locality: "Indiranagar, Bangalore" },
          offers: [
            { title: "Recommended options in Nightlife" },
            { title: "Near Daffy's Brewgarden" },
            { title: "More American restaurants" },
            { title: "Photos" },
          ],
        }}
      />,
    );
    expect(html).not.toContain("Offers");
    expect(html).not.toContain("Recommended options in Nightlife");
    expect(html).not.toContain("Near Daffy's Brewgarden");
    expect(html).not.toContain("More American restaurants");
  });

  it("does not include a delete catalogue control", () => {
    const html = renderToStaticMarkup(<DineoutVenueView venue={dineout.dineout!} />);
    expect(html).not.toContain("Delete Catalogue");
    const pagePath = join(dirname(fileURLToPath(import.meta.url)), "../app/(dashboard)/catalogues/[id]/page.tsx");
    const source = readFileSync(pagePath, "utf8");
    expect(source).not.toContain("DeleteCatalogueButton");
    expect(source).not.toContain("Delete Catalogue");
  });

  it("shows the venue photo instead of the close-icon placeholder", () => {
    const html = renderToStaticMarkup(
      <DineoutVenueView
        venue={{
          venue: "Daffy's Brewgarden",
          hero_image:
            "https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/c62bce32-a7b8-46d8-800b-7ee59ba84114_image2be7594d5b34446ac9171f7bbbf270eeb.JPG",
          photos: [
            "https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/c62bce32-a7b8-46d8-800b-7ee59ba84114_image2be7594d5b34446ac9171f7bbbf270eeb.JPG",
            "https://media-assets.swiggy.com/swiggy/image/upload/fl_lossy,f_auto,q_auto/seo%20web/cross.png",
          ],
          gallery_images: [
            {
              url: "https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/c62bce32-a7b8-46d8-800b-7ee59ba84114_image2be7594d5b34446ac9171f7bbbf270eeb.JPG",
              category: "ambience",
            },
            { url: "https://media-assets.swiggy.com/swiggy/image/upload/fl_lossy,f_auto,q_auto/seo%20web/cross.png" },
          ],
        }}
      />,
    );
    expect(html).toContain("Photos");
    expect(html).toContain("image2be7594d5b34446ac9171f7bbbf270eeb");
    expect(html).not.toContain("cross.png");
  });

  it("shows every PhotoWidget venue slide in the Photos grid", () => {
    const urls = [
      "https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/c62bce32-a7b8-46d8-800b-7ee59ba84114_image2be7594d5b34446ac9171f7bbbf270eeb.JPG",
      "https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/f114b810-13a1-4e79-b217-48e6881b6a8f_image111dea49d524a94d46b04938836c60353f.JPG",
      "https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/943359f5-ca18-4059-b8c5-d96d54017f57_image1049f8418eef2041bca93baa13b2f38cbe.JPG",
      "https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/3059fe66-8df9-4fea-bc89-d2703ba94a96_image9236eba6ed2f04c0d96df24b6a1ec3f5a.JPG",
      "https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/667140e2-f901-4b6f-bc53-122975e416a6_image14ba064c834da9415fbd9eb7de472998cb.JPG",
      "https://dineout-media-assets.swiggy.com/swiggy/image/upload/DINEOUT_ALL_RESTAURANTS/IMAGES/RESTAURANT_IMAGE_SERVICE/2025/10/24/29104a88-2b13-48c8-825e-2b49aba2a652_image24a389b5ef505442fb823953affdc1463f.JPG",
    ];
    const html = renderToStaticMarkup(
      <DineoutVenueView
        venue={{
          venue: "Daffy's Brewgarden",
          hero_image: urls[0],
          photos: urls,
          gallery_images: urls.map((url, index) => ({ url, category: index === 0 ? "ambience" : "venue" })),
        }}
      />,
    );
    expect(html).toContain("Photos");
    for (const url of urls) {
      expect(html).toContain(url.split("/").pop()!.slice(0, 20));
    }
    expect(html).not.toContain("cross.png");
  });

  it("does not invent amenities or offers", () => {
    const html = renderToStaticMarkup(
      <DineoutVenueView venue={{ venue: "Quiet Cafe", location: { address: "MG Road" } }} />,
    );
    expect(html).toContain("Quiet Cafe");
    expect(html).not.toContain("Offers for you");
    expect(html).not.toContain("Amenities");
    expect(html).not.toContain("Popular dishes");
  });

  it("omits implausible distance and keeps the map large and clickable", () => {
    const html = renderToStaticMarkup(
      <DineoutVenueView
        venue={{
          venue: "Daffy's Brewgarden",
          hero_image: "https://cdn.example/hero.jpg",
          photos: ["https://cdn.example/hero.jpg", "https://cdn.example/photo-2.jpg"],
          gallery_images: [
            { url: "https://cdn.example/hero.jpg", category: "ambience" },
            { url: "https://cdn.example/photo-2.jpg", category: "interior" },
          ],
          location: {
            locality: "Indiranagar, Bangalore",
            address: "Plot No. 48, Ground Floor, 100 Feet Road, Defence Colony, Indiranagar, Bangalore, Karnataka",
            distance: "349.5 km",
            maps_url: "https://www.google.com/maps?q=12.97,77.64",
          },
          location_map_image: "https://cdn.example/map.jpg",
          directions_url: "https://www.google.com/maps/dir/?api=1&destination=12.97,77.64",
        }}
      />,
    );
    expect(html).toContain("Location");
    expect(html).toContain("h-[280px]");
    expect(html).toContain("cdn.example/map.jpg");
    expect(html).toContain("Plot No. 48");
    expect(html).toContain("Open in Maps");
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain("cdn.example/photo-2.jpg");
    expect(html).not.toContain("349.5 km");
    expect(html).not.toContain("Delete Catalogue");
  });

  it("uses one Directions control when maps and directions are the same URL", () => {
    const html = renderToStaticMarkup(
      <DineoutVenueView
        venue={{
          venue: "Bob's Bar",
          location: {
            locality: "Indiranagar, Bangalore",
            maps_url: "https://www.google.com/maps?q=12.96710793,77.64128275",
          },
          directions_url: "https://www.google.com/maps?q=12.96710793,77.64128275",
          actions: { directions: "https://www.google.com/maps?q=12.96710793,77.64128275" },
        }}
      />,
    );
    expect(html).toContain("Directions");
    expect(html).not.toContain("Open in Maps");
    expect((html.match(/Directions/g) || []).length).toBeGreaterThanOrEqual(1);
  });

  it("shows dineout view instead of restaurant filters when there are no items", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={dineout} />);
    expect(html).toContain("Brewgarden");
    expect(html).not.toContain("Best Seller");
    expect(html).not.toContain("About Restaurant");
  });
});

describe("overview catalogue cards", () => {
  it("shows dineout metrics that exist", () => {
    const item: StoredCatalogue = {
      id: "d1",
      organizationId: "org",
      createdAt: "2026-01-01T00:00:00Z",
      result: dineout,
    };
    const html = renderToStaticMarkup(<OverviewCatalogueCard item={item} />);
    expect(html).toContain("Brewgarden");
    expect(html).toContain("Dineout");
    expect(html).toContain("Offers: 1");
    expect(html).toContain("Menu sections: 1");
    expect(html).toContain("Photos: 2");
    expect(html).toContain("View Catalogue");
  });

  it("keeps old restaurant catalogues compatible", () => {
    const item: StoredCatalogue = {
      id: "r1",
      organizationId: "org",
      createdAt: "2026-01-01T00:00:00Z",
      result: {
        extraction_status: "ok",
        restaurant_name: "Harbor Spice House",
        fssai_number: "123",
        source_url: "https://www.swiggy.com/city/x/y-rest1",
        restaurant: { name: "Harbor Spice House", outlet: "Sample Road" },
        item_count: 12,
        image_count: 8,
      },
    };
    const html = renderToStaticMarkup(<OverviewCatalogueCard item={item} />);
    expect(html).toContain("Harbor Spice House");
    expect(html).toContain("Sample Road");
    expect(html).toContain("Restaurant");
    expect(html).toContain("12 items");
    expect(html).toContain("8 images");
  });
});
