"use client";

import * as Dialog from "@radix-ui/react-dialog";
import {
  CameraIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  Cross2Icon,
  ExternalLinkIcon,
  ImageIcon,
  LightningBoltIcon,
  MobileIcon,
  ReaderIcon,
  SewingPinIcon,
  StarIcon,
} from "@radix-ui/react-icons";
import { useEffect, useMemo, useRef, useState } from "react";
import { CatalogueImage } from "@/components/catalogue-image";
import { Button } from "@/components/ui/button";
import { isDiscoveryOfferTitle, plausibleVenueDistance, presentText } from "@/lib/restaurant-identity";
import type { DineoutGalleryImage, DineoutVenue } from "@/lib/catalog-types";

function isCatalogueImageSrc(url: string): boolean {
  return /^https?:\/\//i.test(url) || url.startsWith("/catalogue-assets/");
}

function isJunkVenuePhoto(url: string): boolean {
  const text = url.toLowerCase();
  return [
    "iconleft",
    "iconright",
    "cross.png",
    "seo%20web",
    "seo web",
    "plus_icon",
    "popular_dishes.png",
    "rx_highlight",
    "oneexclusive",
    "marketing_banners",
  ].some((hint) => text.includes(hint));
}

function galleryUrls(venue: DineoutVenue): DineoutGalleryImage[] {
  const items = venue.gallery_images?.length
    ? venue.gallery_images
    : (venue.photos || []).map((url) => ({ url }));
  return items.filter((item) => isCatalogueImageSrc(item.url) && !isJunkVenuePhoto(item.url));
}

function menuImages(page: NonNullable<DineoutVenue["menu_pages"]>[number]): string[] {
  const urls = [...(page.images || [])];
  if (page.image) {
    urls.unshift(page.image);
  }
  return [...new Set(urls.filter((url) => isCatalogueImageSrc(url)))];
}

export function DineoutVenueView({ venue }: { venue: DineoutVenue }) {
  const name = presentText(venue.venue);
  const location =
    presentText(venue.location?.outlet) ||
    presentText(venue.location?.locality) ||
    presentText(venue.location?.location) ||
    presentText(venue.location?.address);
  const cuisines = (venue.cuisines || []).map((item) => item.trim()).filter(Boolean);
  const offers = (venue.offers || []).filter(
    (offer) => presentText(offer.title) && !isDiscoveryOfferTitle(offer.title),
  );
  const menuPages = venue.menu_pages || [];
  const photos = galleryUrls(venue);
  const amenities = (venue.amenities || []).map((item) => item.trim()).filter(Boolean);
  const popular = (venue.popular_dishes || []).map((item) => item.trim()).filter(Boolean);
  const directions = presentText(venue.directions_url) || presentText(venue.actions?.directions);
  const call = presentText(venue.phone) || presentText(venue.actions?.call);
  const hours = presentText(venue.opening_status) || presentText(venue.opening_hours);
  const price = presentText(venue.price_for_two);
  const address = presentText(venue.location?.address);
  const distance = plausibleVenueDistance(venue.location?.distance);
  const mapImage = presentText(venue.location_map_image) || presentText(venue.location?.map_image);
  const mapsUrl = presentText(venue.location?.maps_url) || presentText(venue.directions_url) || presentText(venue.actions?.directions);
  const hero = presentText(venue.hero_image) || photos[0]?.url || null;
  const slides = useMemo(() => {
    const items = [...photos];
    if (hero && !items.some((item) => item.url === hero)) {
      items.unshift({ url: hero, category: "ambience" });
    }
    return items;
  }, [photos, hero]);
  const gridPhotos = slides;
  const [index, setIndex] = useState<number | null>(null);
  const [menuPreview, setMenuPreview] = useState<{ src: string; title: string } | null>(null);

  useEffect(() => {
    if (index == null) {
      return;
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "ArrowRight") {
        setIndex((current) => (current == null ? current : (current + 1) % slides.length));
      }
      if (event.key === "ArrowLeft") {
        setIndex((current) => (current == null ? current : (current - 1 + slides.length) % slides.length));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, slides.length]);

  return (
    <div className="space-y-10">
      <section className="overflow-hidden rounded-2xl border border-border bg-card">
        {hero ? (
          <div className="relative aspect-[4/3] bg-muted phone:aspect-[16/8] laptop:aspect-[21/9]">
            <CatalogueImage src={hero} alt={name || "Ambience"} className="size-full object-cover" />
            {slides.length ? (
              <Button
                type="button"
                variant="secondary"
                className="absolute bottom-4 right-4"
                onClick={() => setIndex(Math.max(0, slides.findIndex((item) => item.url === hero)))}
              >
                <CameraIcon />
                View all images
              </Button>
            ) : null}
          </div>
        ) : null}
        <div className="space-y-4 p-5 phone:p-6">
          {name ? <h2 className="text-2xl font-medium tracking-tight phone:text-3xl">{name}</h2> : null}
          {location ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <SewingPinIcon />
              {location}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {venue.rating != null ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-sm">
                <StarIcon />
                {venue.rating}
                {presentText(venue.rating_count) ? ` · ${venue.rating_count}` : ""}
              </span>
            ) : null}
            {price ? (
              <span className="rounded-full border border-border px-3 py-1 text-sm text-muted-foreground">{price}</span>
            ) : null}
            {hours ? (
              <span className="rounded-full border border-border px-3 py-1 text-sm text-muted-foreground">{hours}</span>
            ) : null}
          </div>
          {cuisines.length ? (
            <ul className="flex flex-wrap gap-2">
              {cuisines.map((cuisine) => (
                <li key={cuisine} className="rounded-full bg-muted px-3 py-1 text-sm">
                  {cuisine}
                </li>
              ))}
            </ul>
          ) : null}
          {directions || call ? (
            <div className="flex flex-wrap gap-2">
              {directions ? (
                <Button asChild variant="outline">
                  <a href={directions} target="_blank" rel="noopener noreferrer">
                    <ExternalLinkIcon />
                    Directions
                  </a>
                </Button>
              ) : null}
              {call ? (
                <Button asChild variant="outline">
                  <a href={`tel:${call.replace(/\s+/g, "")}`}>
                    <MobileIcon />
                    Call
                  </a>
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      </section>

      {offers.length ? (
        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-lg font-medium">
            <LightningBoltIcon /> Offers
          </h3>
          <OfferCarousel offers={offers} />
        </section>
      ) : null}

      {popular.length ? (
        <section className="space-y-3">
          <h3 className="text-lg font-medium">Popular dishes</h3>
          <ul className="flex flex-wrap gap-2">
            {popular.map((dish) => (
              <li key={dish} className="rounded-full border border-border px-3 py-1 text-sm">
                {dish}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {cuisines.length ? (
        <section className="space-y-3">
          <h3 className="text-lg font-medium">Cuisines</h3>
          <ul className="flex flex-wrap gap-2">
            {cuisines.map((cuisine) => (
              <li key={cuisine} className="rounded-full bg-muted px-3 py-1 text-sm">
                {cuisine}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {menuPages.length ? (
        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-lg font-medium">
            <ReaderIcon /> Menu
          </h3>
          <div className="grid gap-3 phone:grid-cols-2 laptop:grid-cols-3">
            {menuPages.map((page, index) => {
              const images = menuImages(page);
              const pages = page.page_count || images.length || 0;
              return (
                <article
                  key={page.identity || `${page.title}-${index}`}
                  className="overflow-hidden rounded-xl border border-border bg-card"
                >
                  {images[0] ? (
                    <button
                      type="button"
                      className="block w-full"
                      onClick={() => setMenuPreview({ src: images[0], title: page.title })}
                    >
                      <CatalogueImage src={images[0]} alt={page.title} className="aspect-[3/4] w-full object-cover" />
                    </button>
                  ) : null}
                  <div className="p-3">
                    <p className="font-medium">{page.title}</p>
                    {pages ? (
                      <p className="text-sm text-muted-foreground">
                        {pages} page{pages === 1 ? "" : "s"}
                      </p>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      {gridPhotos.length ? (
        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-lg font-medium">
            <CameraIcon /> Photos
          </h3>
          <div className="grid grid-cols-2 gap-3 laptop:grid-cols-3">
            {gridPhotos.map((item) => (
              <button
                key={item.url}
                type="button"
                className="overflow-hidden rounded-xl border border-border"
                onClick={() => setIndex(Math.max(0, slides.findIndex((slide) => slide.url === item.url)))}
              >
                <CatalogueImage
                  src={item.url}
                  alt={item.category || "Venue photo"}
                  className="aspect-[4/3] w-full object-cover"
                />
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {(venue.videos || []).filter((item) => item.source_url).length ? (
        <section className="space-y-3">
          <h3 className="text-lg font-medium">Videos</h3>
          <ul className="space-y-3">
            {(venue.videos || []).filter((item) => item.source_url).map((item) => (
              <li key={item.source_url} className="overflow-hidden rounded-xl border border-border">
                <video className="w-full" controls src={item.source_url} poster={item.thumbnail || undefined} />
                {item.title ? <p className="p-2 text-sm text-muted-foreground">{item.title}</p> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {amenities.length ? (
        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-lg font-medium">
            <CheckIcon /> Amenities
          </h3>
          <ul className="grid gap-2 phone:grid-cols-2">
            {amenities.map((item) => (
              <li key={item} className="flex items-center gap-2 text-sm">
                <CheckIcon className="text-muted-foreground" />
                {item}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {address || location || mapImage || mapsUrl ? (
        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-lg font-medium">
            <SewingPinIcon /> Location
          </h3>
          <div className="overflow-hidden rounded-2xl border border-border bg-card">
            {mapImage ? (
              mapsUrl ? (
                <a href={mapsUrl} target="_blank" rel="noopener noreferrer" className="relative block w-full">
                  <CatalogueImage
                    src={mapImage}
                    alt="Location map"
                    className="h-[280px] w-full object-cover laptop:h-[360px]"
                  />
                  <span className="absolute bottom-4 right-4 inline-flex items-center gap-1 rounded-full border border-border bg-card/90 px-3 py-1.5 text-sm shadow-sm backdrop-blur-sm">
                    Open in Maps
                    <ExternalLinkIcon />
                  </span>
                </a>
              ) : (
                <CatalogueImage
                  src={mapImage}
                  alt="Location map"
                  className="h-[280px] w-full object-cover laptop:h-[360px]"
                />
              )
            ) : null}
            <div className="space-y-3 p-5">
              {location ? <p className="text-lg font-medium">{location}</p> : null}
              {address && address !== location ? (
                <p className="whitespace-pre-line text-sm leading-6 text-muted-foreground">{address}</p>
              ) : null}
              {distance ? <p className="text-sm text-muted-foreground">{distance}</p> : null}
              {mapsUrl || directions ? (
                <div className="flex flex-col gap-2 phone:flex-row phone:flex-wrap">
                  {mapsUrl && directions && mapsUrl !== directions ? (
                    <>
                      <Button asChild variant="outline">
                        <a href={mapsUrl} target="_blank" rel="noopener noreferrer">
                          <ExternalLinkIcon />
                          Open in Maps
                        </a>
                      </Button>
                      <Button asChild variant="outline">
                        <a href={directions} target="_blank" rel="noopener noreferrer">
                          <ExternalLinkIcon />
                          Directions
                        </a>
                      </Button>
                    </>
                  ) : (
                    <Button asChild variant="outline">
                      <a href={mapsUrl || directions || ""} target="_blank" rel="noopener noreferrer">
                        <ExternalLinkIcon />
                        Directions
                      </a>
                    </Button>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      <section className="space-y-3">
        <h3 className="flex items-center gap-2 text-lg font-medium">
          <ImageIcon /> About Dineout
        </h3>
        <DineoutFacts venue={venue} />
      </section>

      <Dialog.Root open={index != null && slides.length > 0} onOpenChange={(open) => !open && setIndex(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
          <Dialog.Content
            className="fixed left-1/2 top-1/2 z-50 w-[min(56rem,calc(100vw-1.5rem))] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-3"
            onKeyDown={(event) => {
              if (event.key === "ArrowRight" && slides.length) {
                setIndex((current) => ((current ?? 0) + 1) % slides.length);
              }
              if (event.key === "ArrowLeft" && slides.length) {
                setIndex((current) => ((current ?? 0) - 1 + slides.length) % slides.length);
              }
            }}
          >
            <div className="mb-2 flex items-center justify-between gap-3">
              <Dialog.Title className="text-sm font-medium">
                {index != null ? `${index + 1} / ${slides.length}` : "Photos"}
              </Dialog.Title>
              <Dialog.Close asChild>
                <Button type="button" size="icon" variant="ghost">
                  <Cross2Icon />
                </Button>
              </Dialog.Close>
            </div>
            {index != null && slides[index] ? (
              <div className="relative">
                <CatalogueImage
                  src={slides[index].url}
                  alt={slides[index].category || name || "Photo"}
                  className="max-h-[80vh] w-full rounded-xl object-contain"
                />
                {slides.length > 1 ? (
                  <>
                    <Button
                      type="button"
                      size="icon"
                      variant="secondary"
                      className="absolute left-2 top-1/2 -translate-y-1/2"
                      onClick={() => setIndex((current) => ((current ?? 0) - 1 + slides.length) % slides.length)}
                    >
                      <ChevronLeftIcon />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="secondary"
                      className="absolute right-2 top-1/2 -translate-y-1/2"
                      onClick={() => setIndex((current) => ((current ?? 0) + 1) % slides.length)}
                    >
                      <ChevronRightIcon />
                    </Button>
                  </>
                ) : null}
              </div>
            ) : null}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={Boolean(menuPreview)} onOpenChange={(open) => !open && setMenuPreview(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(56rem,calc(100vw-1.5rem))] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-3">
            <div className="mb-2 flex items-center justify-between gap-3">
              <Dialog.Title className="text-sm font-medium">{menuPreview?.title}</Dialog.Title>
              <Dialog.Close asChild>
                <Button type="button" size="icon" variant="ghost">
                  <Cross2Icon />
                </Button>
              </Dialog.Close>
            </div>
            {menuPreview ? (
              <CatalogueImage src={menuPreview.src} alt={menuPreview.title} className="max-h-[80vh] w-full rounded-xl object-contain" />
            ) : null}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}

function OfferCarousel({ offers }: { offers: NonNullable<DineoutVenue["offers"]> }) {
  const scroller = useRef<HTMLDivElement>(null);

  function scrollByCard(direction: number) {
    const node = scroller.current;
    if (!node) {
      return;
    }
    node.scrollBy({ left: direction * 280, behavior: "smooth" });
  }

  return (
    <div className="relative">
      {offers.length > 1 ? (
        <>
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className="absolute left-0 top-1/2 z-10 hidden -translate-y-1/2 phone:inline-flex"
            onClick={() => scrollByCard(-1)}
            aria-label="Previous offers"
          >
            <ChevronLeftIcon />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className="absolute right-0 top-1/2 z-10 hidden -translate-y-1/2 phone:inline-flex"
            onClick={() => scrollByCard(1)}
            aria-label="Next offers"
          >
            <ChevronRightIcon />
          </Button>
        </>
      ) : null}
      <div ref={scroller} className="flex gap-3 overflow-x-auto pb-2 scroll-smooth snap-x snap-mandatory">
        {offers.map((offer, index) => {
          const image = presentText(offer.image);
          const description = presentText(offer.description) || presentText(offer.discount) || presentText(offer.code);
          const kind = presentText(offer.type) || "Offer";
          return (
            <article
              key={`${offer.title}-${index}`}
              data-flash-offer="true"
              className="w-[280px] shrink-0 snap-start overflow-hidden rounded-2xl border border-amber-500/40 bg-gradient-to-br from-amber-50 via-card to-orange-100 shadow-sm dark:from-amber-950 dark:via-card dark:to-neutral-900"
            >
              {image ? (
                <CatalogueImage src={image} alt={offer.title} className="h-28 w-full object-cover" fallbackClassName="h-28 w-full" />
              ) : (
                <div className="flex h-20 items-center justify-center bg-gradient-to-r from-amber-400/80 to-orange-500/80 px-3 text-center text-[11px] font-semibold uppercase tracking-[0.18em] text-neutral-950">
                  {kind}
                </div>
              )}
              <div className="space-y-1 p-4">
                {image ? <p className="text-[11px] font-medium uppercase tracking-wide text-amber-700 dark:text-amber-400">{kind}</p> : null}
                <p className="line-clamp-2 text-base font-semibold">{offer.title}</p>
                {description ? <p className="line-clamp-3 text-xs leading-5 text-muted-foreground">{description}</p> : null}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function DineoutFacts({ venue }: { venue: DineoutVenue }) {
  const rows = [
    ["Restaurant name", presentText(venue.venue)],
    ["Restaurant ID", presentText(venue.restaurant_id)],
    ["Location", presentText(venue.location?.outlet) || presentText(venue.location?.locality)],
    ["Address", presentText(venue.location?.address)],
    ["Rating", venue.rating != null ? String(venue.rating) : null],
    ["Rating count", presentText(venue.rating_count)],
    ["Cuisine", (venue.cuisines || []).filter(Boolean).join(", ") || null],
    ["Price for two", presentText(venue.price_for_two)],
    ["Phone", presentText(venue.phone) || presentText(venue.actions?.call)],
    ["Opening status", presentText(venue.opening_status) || presentText(venue.opening_hours)],
    ["Source URL", presentText(venue.source_url)],
  ].filter((row): row is [string, string] => Boolean(row[1]));
  if (!rows.length) {
    return null;
  }
  return (
    <dl className="grid gap-3 text-sm laptop:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="break-all font-medium">
            {/^https?:\/\//i.test(value) ? (
              <a href={value} target="_blank" rel="noopener noreferrer" className="hover:underline">
                {value}
              </a>
            ) : (
              value
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}
