"use client";

import { Cross2Icon, MagnifyingGlassIcon, MinusIcon, PlusIcon } from "@radix-ui/react-icons";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CatalogueImage } from "@/components/catalogue-image";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { catalogueMediaHref } from "@/lib/media-ui";
import {
  ALL_CATEGORIES,
  FOOD_FILTER_ALL,
  FOOD_FILTER_NONVEG,
  FOOD_FILTER_VEG,
  categoryAnchor,
  customizationGroups,
  discountLabel,
  filterCatalogue,
  findItemByKey,
  formatPrice,
  hasProductImage,
  identifyCatalogue,
  isBestseller,
  isCustomizable,
  isItemAvailable,
  isVeg,
  itemCount,
  nextAvailableLabel,
  sellingAmount,
  variantGroups,
  type FoodFilter,
  type IdentifiedCategory,
  type IdentifiedItem,
  type ImageFilter,
} from "@/lib/catalogue-menu";
import {
  addCartLine,
  cartTotal,
  extrasTotal,
  lineSubtotal,
  lineUnitTotal,
  removeCartLine,
  setCartQuantity,
  type CartExtra,
  type CartLine,
} from "@/lib/catalogue-cart";
import { AboutFields } from "@/components/about-fields";
import { CustomerFeedbackForm } from "@/components/customer-feedback-form";
import { DineoutVenueView } from "@/components/dineout-venue-view";
import {
  catalogueType,
  resolveDineout,
  restaurantDisplayName,
  restaurantLocation,
  venueDisplayName,
} from "@/lib/restaurant-identity";
import { cataloguePlatform, extractionMessage, type CatalogCreateResponse } from "@/lib/catalog-types";
import { cn } from "@/lib/utils";

export function CatalogueLoading() {
  return <p className="text-sm text-muted-foreground">Loading catalogue…</p>;
}

export function CatalogueView({
  catalogue,
  initialQuery = "",
  initialCategory = ALL_CATEGORIES,
  initialFoodFilter = FOOD_FILTER_ALL,
  initialImageFilter = "all",
  initialBestseller = false,
  openItemName,
  openItemKey,
  feedbackContext,
}: {
  catalogue: CatalogCreateResponse;
  initialQuery?: string;
  initialCategory?: string;
  initialFoodFilter?: FoodFilter;
  initialImageFilter?: ImageFilter;
  initialBestseller?: boolean;
  openItemName?: string;
  openItemKey?: string;
  feedbackContext?: { catalogueId: string; organizationId: string };
}) {
  const status = catalogue.extraction_status;
  if (status === "blocked") {
    return (
      <div className="space-y-2 rounded-xl border border-border bg-card p-6 text-card-foreground">
        <h2 className="text-lg font-medium">
          {extractionMessage("blocked", null, cataloguePlatform(catalogue))}
        </h2>
        {catalogue.error ? <p className="text-sm text-muted-foreground">{catalogue.error}</p> : null}
      </div>
    );
  }
  if (status !== "ok") {
    return (
      <div className="space-y-2 rounded-xl border border-border bg-card p-6 text-card-foreground">
        <h2 className="text-lg font-medium">Catalogue not available</h2>
        {catalogue.error ? <p className="text-sm text-muted-foreground">{catalogue.error}</p> : null}
      </div>
    );
  }

  const type = catalogueType(catalogue.catalogue_type);
  const dineout = resolveDineout(catalogue);
  const hasItems =
    (catalogue.item_count || 0) > 0 || Boolean(catalogue.categories?.some((category) => category.items.length));
  const showMenu = type === "restaurant" || type === "both" || hasItems;
  const showRestaurantAbout = type === "restaurant" || type === "both";
  return (
    <div className="space-y-10">
      {feedbackContext ? (
        <CustomerFeedbackForm
          catalogueId={feedbackContext.catalogueId}
          organizationId={feedbackContext.organizationId}
          restaurantName={venueDisplayName(catalogue)}
        />
      ) : null}
      {dineout && (type === "dineout" || type === "both") ? <DineoutVenueView venue={dineout} /> : null}
      {showMenu ? (
        <CatalogueMenu
          catalogue={catalogue}
          initialQuery={initialQuery}
          initialCategory={initialCategory}
          initialFoodFilter={initialFoodFilter}
          initialImageFilter={initialImageFilter}
          initialBestseller={initialBestseller}
          openItemName={openItemName}
          openItemKey={openItemKey}
        />
      ) : null}
      {showRestaurantAbout ? (
        <section className="space-y-3 rounded-2xl border border-border bg-card p-6">
          <h2 className="text-lg font-medium">About Restaurant</h2>
          <AboutFields
            restaurant={catalogue.restaurant}
            restaurantName={catalogue.restaurant_name}
            fssaiNumber={catalogue.fssai_number}
            sourceUrl={catalogue.source_url}
          />
        </section>
      ) : null}
    </div>
  );
}

function CatalogueMenu({
  catalogue,
  initialQuery,
  initialCategory,
  initialFoodFilter,
  initialImageFilter,
  initialBestseller,
  openItemName,
  openItemKey,
}: {
  catalogue: CatalogCreateResponse;
  initialQuery: string;
  initialCategory: string;
  initialFoodFilter: FoodFilter;
  initialImageFilter: ImageFilter;
  initialBestseller: boolean;
  openItemName?: string;
  openItemKey?: string;
}) {
  const identified = useMemo(() => identifyCatalogue(catalogue.categories ?? []), [catalogue.categories]);
  const [query, setQuery] = useState(initialQuery);
  const [selectedCategory, setSelectedCategory] = useState(() => resolveCategoryKey(identified, initialCategory));
  const [foodFilter, setFoodFilter] = useState<FoodFilter>(initialFoodFilter);
  const [imageFilter, setImageFilter] = useState<ImageFilter>(initialImageFilter);
  const [bestsellerOnly, setBestsellerOnly] = useState(initialBestseller);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [cartOpen, setCartOpen] = useState(false);
  const [addedLine, setAddedLine] = useState<CartLine | null>(null);
  const [activeItemKey, setActiveItemKey] = useState<string | null>(() => {
    if (openItemKey) {
      return openItemKey;
    }
    if (!openItemName) {
      return null;
    }
    return identified.flatMap((category) => category.items).find((item) => item.name === openItemName)?.key ?? null;
  });

  const filtered = useMemo(
    () => filterCatalogue(identified, query, selectedCategory, foodFilter, imageFilter, bestsellerOnly),
    [identified, query, selectedCategory, foodFilter, imageFilter, bestsellerOnly],
  );
  const totalItems = catalogue.item_count ?? itemCount(identified);
  const restaurantName = restaurantDisplayName(catalogue.restaurant, catalogue.restaurant_name);
  const location = restaurantLocation(catalogue.restaurant);
  const activeItem = findItemByKey(identified, activeItemKey);

  useEffect(() => {
    if (selectedCategory === ALL_CATEGORIES) {
      return;
    }
    const category = identified.find((entry) => entry.key === selectedCategory);
    if (!category) {
      return;
    }
    document.getElementById(categoryAnchor(category.name, category.sourceIndex))?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, [selectedCategory, identified, filtered]);

  function selectCategory(key: string) {
    setSelectedCategory(key);
  }

  function changeCartQuantity(lineId: string, quantity: number) {
    setCart(setCartQuantity(cart, lineId, quantity));
  }

  return (
    <div className="space-y-6 text-foreground" data-testid="catalogue-view">
      <RestaurantHero
        catalogue={catalogue}
        restaurantName={restaurantName}
        location={location}
        categoryCount={identified.filter((category) => category.items.length).length}
        itemCount={totalItems}
      />

      {identified.length === 0 || totalItems === 0 ? (
        <p className="rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">
          No menu items were available in this catalogue.
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-3 laptop:flex-row laptop:items-center laptop:justify-between">
            <div className="flex min-w-0 flex-1 flex-col gap-3">
              <div className="relative max-w-md">
                <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search the menu"
                  aria-label="Search the menu"
                  className="pl-9"
                />
              </div>
              <CatalogueFilterControl
                foodFilter={foodFilter}
                imageFilter={imageFilter}
                bestsellerOnly={bestsellerOnly}
                onFoodFilter={setFoodFilter}
                onImageFilter={setImageFilter}
                onBestseller={setBestsellerOnly}
              />
            </div>
            <div className="flex items-center gap-3">
              <p className="text-sm text-muted-foreground">
                Showing {itemCount(filtered)} of {totalItems} items
              </p>
            </div>
          </div>

          <div className="laptop:grid laptop:grid-cols-[220px_minmax(0,1fr)] laptop:gap-8">
            <CategoryNav categories={identified} selected={selectedCategory} onSelect={selectCategory} />
            <div className="min-h-0 min-w-0 space-y-10">
              {filtered.length === 0 ? (
                <p className="text-sm text-muted-foreground">No items match your search.</p>
              ) : (
                filtered.map((category) => (
                  <CategorySection
                    key={category.key}
                    category={category}
                    anchor={categoryAnchor(category.name, category.sourceIndex)}
                    onOpenItem={(item) => setActiveItemKey(item.key)}
                  />
                ))
              )}
            </div>
          </div>
        </>
      )}

      {cart.length > 0 && !cartOpen ? (
        <button
          type="button"
          className="fixed bottom-6 right-6 z-[90] flex max-w-[min(16rem,calc(100vw-2rem))] items-center gap-2 rounded-full border border-border bg-popover px-3 py-2 text-left text-popover-foreground shadow-lg"
          aria-label={`Cart (${cart.reduce((sum, line) => sum + line.quantity, 0)})`}
          onClick={() => {
            setAddedLine(null);
            setCartOpen(true);
          }}
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-foreground text-sm font-medium text-background">
            {cart.reduce((sum, line) => sum + line.quantity, 0)}
          </span>
          <span className="min-w-0 pr-1">
            <span className="block text-xs font-medium">Cart</span>
            <span className="block truncate text-[11px] text-muted-foreground">
              {addedLine ? `${addedLine.name} × ${addedLine.quantity}` : formatPrice(cartTotal(cart))}
            </span>
          </span>
        </button>
      ) : null}

      {cartOpen ? (
        <div className="fixed inset-0 z-[80] flex justify-end bg-black/50" onClick={() => setCartOpen(false)}>
          <aside
            className="flex h-full w-full max-w-md flex-col border-l border-border bg-popover text-popover-foreground shadow-lg"
            role="dialog"
            aria-label="Cart"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="text-sm font-medium">Cart</h2>
              <button type="button" aria-label="Close cart" onClick={() => setCartOpen(false)} className="rounded-md p-1 hover:bg-accent">
                <Cross2Icon />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {cart.length ? (
                <CartPanel
                  lines={cart}
                  onQuantity={changeCartQuantity}
                  onRemove={(id) => setCart(removeCartLine(cart, id))}
                />
              ) : (
                <p className="text-sm text-muted-foreground">Your cart is empty.</p>
              )}
            </div>
          </aside>
        </div>
      ) : null}

      {activeItem ? (
        <ItemDetail
          key={activeItem.key}
          item={activeItem}
          onClose={() => setActiveItemKey(null)}
          onAdd={(extras) => {
            const next = addCartLine(cart, {
              itemKey: activeItem.key,
              name: activeItem.name,
              unitPrice: sellingAmount(activeItem),
              extras,
            });
            setCart(next);
            setAddedLine(next.find((line) => line.itemKey === activeItem.key) || next[next.length - 1]);
            setActiveItemKey(null);
          }}
        />
      ) : null}
    </div>
  );
}

function resolveCategoryKey(categories: IdentifiedCategory[], selected: string): string {
  if (selected === ALL_CATEGORIES) {
    return ALL_CATEGORIES;
  }
  if (categories.some((category) => category.key === selected)) {
    return selected;
  }
  return categories.find((category) => category.name === selected)?.key ?? ALL_CATEGORIES;
}

function CatalogueFilterControl({
  foodFilter,
  imageFilter,
  bestsellerOnly,
  onFoodFilter,
  onImageFilter,
  onBestseller,
}: {
  foodFilter: FoodFilter;
  imageFilter: ImageFilter;
  bestsellerOnly: boolean;
  onFoodFilter: (value: FoodFilter) => void;
  onImageFilter: (value: ImageFilter) => void;
  onBestseller: (value: boolean) => void;
}) {
  const chips: Array<{ id: string; label: string; active: boolean; onClick: () => void }> = [
    {
      id: "all",
      label: "All",
      active: foodFilter === FOOD_FILTER_ALL && imageFilter === "all" && !bestsellerOnly,
      onClick: () => {
        onFoodFilter(FOOD_FILTER_ALL);
        onImageFilter("all");
        onBestseller(false);
      },
    },
    { id: "veg", label: "Veg", active: foodFilter === FOOD_FILTER_VEG, onClick: () => onFoodFilter(FOOD_FILTER_VEG) },
    { id: "nonveg", label: "Non-Veg", active: foodFilter === FOOD_FILTER_NONVEG, onClick: () => onFoodFilter(FOOD_FILTER_NONVEG) },
    { id: "bestseller", label: "Best Seller", active: bestsellerOnly, onClick: () => onBestseller(!bestsellerOnly) },
    {
      id: "with-images",
      label: "With Images",
      active: imageFilter === "with",
      onClick: () => onImageFilter(imageFilter === "with" ? "all" : "with"),
    },
    {
      id: "without-images",
      label: "Without Images",
      active: imageFilter === "without",
      onClick: () => onImageFilter(imageFilter === "without" ? "all" : "without"),
    },
  ];
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Food type filter">
      {chips.map((chip) => (
        <button
          key={chip.id}
          type="button"
          onClick={chip.onClick}
          className={cn(
            "rounded-full border px-3 py-1.5 text-sm transition-colors",
            chip.active
              ? "border-primary bg-primary text-primary-foreground"
              : "border-border bg-background text-foreground hover:bg-accent",
          )}
        >
          {chip.label}
        </button>
      ))}
    </div>
  );
}

function RestaurantHero({
  catalogue,
  restaurantName,
  location,
  categoryCount,
  itemCount: items,
}: {
  catalogue: CatalogCreateResponse;
  restaurantName: string;
  location: string | null;
  categoryCount: number;
  itemCount: number;
}) {
  const restaurant = catalogue.restaurant;
  const cuisines = restaurant?.cuisines?.filter(Boolean) ?? [];
  const firstItemWithImage = catalogue.categories
    ?.flatMap((cat) => cat.items || [])
    ?.find((item) => hasProductImage(item))?.image_url;
  const heroImage =
    restaurant?.image_url ||
    catalogue.dineout?.hero_image ||
    catalogue.dineout?.photos?.[0] ||
    firstItemWithImage;

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card text-card-foreground">
      <div className="relative aspect-[21/9] min-h-40 bg-muted tablet:min-h-48">
        <CatalogueImage
          src={heroImage}
          alt={restaurantName}
          className="h-full w-full object-cover"
          fallbackClassName="h-full w-full dot-matrix bg-zinc-900"
        />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/80 via-black/35 to-black/10" />
        {catalogue.id ? (
          <div className="absolute right-3 top-3 z-10">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="bg-black/60 text-white backdrop-blur-md hover:bg-black/80 border border-white/20 text-xs"
              asChild
            >
              <Link href={catalogueMediaHref(catalogue.id, { path: "restaurant.image_url" })}>
                ✨ Edit Hero with AI
              </Link>
            </Button>
          </div>
        ) : null}
        <div className="absolute inset-x-0 bottom-0 space-y-2 p-4 tablet:p-6">
          <h1 className="text-2xl font-medium tracking-tight text-white tablet:text-3xl">{restaurantName}</h1>
          <div className="flex flex-wrap gap-2 text-sm text-white/80">
            {restaurant?.rating != null ? (
              <span>
                {restaurant.rating}
                {restaurant.rating_count ? ` (${restaurant.rating_count})` : ""}
              </span>
            ) : null}
            {cuisines.length ? <span>{cuisines.join(", ")}</span> : null}
            {restaurant?.price_for_two != null && restaurant.price_for_two !== "" ? (
              <span>{String(restaurant.price_for_two)}</span>
            ) : null}
            {location ? <span>{location}</span> : null}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 border-t border-border px-4 py-3 text-sm text-muted-foreground tablet:px-6">
        <span>Categories: {categoryCount}</span>
        <span>Items: {items}</span>
        {catalogue.image_count != null ? <span>Images: {catalogue.image_count}</span> : null}
      </div>
    </section>
  );
}

function CategoryNav({
  categories,
  selected,
  onSelect,
}: {
  categories: IdentifiedCategory[];
  selected: string;
  onSelect: (key: string) => void;
}) {
  const options = [{ name: "All", value: ALL_CATEGORIES }, ...categories.map((category) => ({ name: category.name, value: category.key }))];

  return (
    <nav className="mb-4 laptop:mb-0" aria-label="Menu categories">
      <div className="flex gap-2 overflow-x-auto pb-2 laptop:hidden">
        {options.map((option) => (
          <CategoryChip
            key={option.value}
            label={option.name}
            active={selected === option.value}
            onClick={() => onSelect(option.value)}
          />
        ))}
      </div>
      <div className="sticky top-4 hidden max-h-[calc(100dvh-8rem)] space-y-1 overflow-y-auto laptop:block">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onSelect(option.value)}
            className={cn(
              "block w-full rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground",
              selected === option.value ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground",
            )}
          >
            {option.name}
          </button>
        ))}
      </div>
    </nav>
  );
}

function CategoryChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "shrink-0 rounded-full border px-3 py-1.5 text-sm transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-background text-foreground hover:bg-accent",
      )}
    >
      {label}
    </button>
  );
}

function CategorySection({
  category,
  anchor,
  onOpenItem,
}: {
  category: IdentifiedCategory;
  anchor: string;
  onOpenItem: (item: IdentifiedItem) => void;
}) {
  return (
    <section id={anchor} data-category-key={category.key} className="scroll-mt-6">
      <h2 className="mb-4 text-xl font-medium">{category.name}</h2>
      {category.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No items in this category.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 tablet:grid-cols-2 laptop:grid-cols-3 desktop:grid-cols-4">
          {category.items.map((item) => (
            <ItemCard key={item.key} item={item} onOpen={() => onOpenItem(item)} />
          ))}
        </div>
      )}
    </section>
  );
}

function ItemCard({ item, onOpen }: { item: IdentifiedItem; onOpen: () => void }) {
  const price = formatPrice(item.price);
  const original = formatPrice(item.original_price);
  const veg = isVeg(item.food_type);
  const discount = discountLabel(item);
  const availability = nextAvailableLabel(item);
  const unavailable = !isItemAvailable(item) || Boolean(availability);

  return (
    <article data-item-key={item.key} className="flex h-full flex-col overflow-hidden rounded-lg border border-border bg-card text-card-foreground transition-colors hover:border-foreground/20">
      <div className="aspect-[4/3] bg-muted">
        <CatalogueImage
          src={hasProductImage(item) ? item.image_url : null}
          alt={item.name}
          className="h-full w-full object-cover"
          fallbackClassName="h-full w-full"
        />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2 p-4">
        <div className="flex items-start gap-2">
          <VegMark veg={veg} />
          <h3 className="min-w-0 flex-1 text-base font-medium leading-snug">{item.name}</h3>
        </div>
        {item.description ? (
          <p className="line-clamp-2 text-sm text-muted-foreground">{item.description}</p>
        ) : null}
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
          {price ? <p className="font-medium">{price}</p> : null}
          {original && original !== price ? (
            <p className="text-sm text-muted-foreground line-through">{original}</p>
          ) : null}
          {discount ? <p className="text-xs text-muted-foreground">{discount}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {isBestseller(item) ? (
            <span className="rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">Best Seller</span>
          ) : null}
          {isCustomizable(item) ? <span className="text-xs text-muted-foreground">Customisable</span> : null}
        </div>
        {unavailable && availability ? (
          <p className="text-xs text-muted-foreground">{availability}</p>
        ) : null}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="relative z-10 mt-1 w-full"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onOpen();
          }}
        >
          View details
        </Button>
      </div>
    </article>
  );
}

function VegMark({ veg }: { veg: boolean | null }) {
  if (veg == null) {
    return null;
  }
  return (
    <span
      className={cn(
        "mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border",
        veg ? "border-emerald-600" : "border-red-600",
      )}
      aria-label={veg ? "Vegetarian" : "Non-vegetarian"}
      title={veg ? "Vegetarian" : "Non-vegetarian"}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", veg ? "bg-emerald-600" : "bg-red-600")} />
    </span>
  );
}

function ItemDetail({
  item,
  onClose,
  onAdd,
}: {
  item: IdentifiedItem;
  onClose: () => void;
  onAdd: (extras: CartExtra[]) => void;
}) {
  const price = formatPrice(item.price);
  const original = formatPrice(item.original_price);
  const veg = isVeg(item.food_type);
  const variants = variantGroups(item);
  const customizations = customizationGroups(item);
  const discount = discountLabel(item);
  const availability = nextAvailableLabel(item);
  const [selected, setSelected] = useState<CartExtra[]>([]);
  const extraCost = extrasTotal(selected);
  const total = sellingAmount(item) + extraCost;

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  function toggleExtra(extra: CartExtra) {
    setSelected((current) => {
      const exists = current.some((entry) => entry.name === extra.name);
      return exists ? current.filter((entry) => entry.name !== extra.name) : [...current, extra];
    });
  }

  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-black/50" onClick={onClose}>
      <aside
        className="flex h-full w-full max-w-md translate-x-0 flex-col border-l border-border bg-popover text-popover-foreground shadow-lg animate-in slide-in-from-right"
        role="dialog"
        aria-modal="true"
        aria-labelledby="item-detail-title"
        data-item-key={item.key}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-medium">Product Details</h2>
          <button type="button" aria-label="Close" onClick={onClose} className="rounded-md p-1 hover:bg-accent">
            <Cross2Icon />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="aspect-[16/10] bg-muted">
            <CatalogueImage
              src={hasProductImage(item) ? item.image_url : null}
              alt={item.name}
              className="h-full w-full object-cover"
              fallbackClassName="h-full w-full"
            />
          </div>
          <div className="space-y-4 p-5">
            <div className="flex items-start gap-2">
              <VegMark veg={veg} />
              <h2 id="item-detail-title" className="text-xl font-medium">
                {item.name}
              </h2>
            </div>
            {veg != null ? <p className="text-sm text-muted-foreground">{veg ? "Veg" : "Non-Veg"}</p> : null}
            {item.description ? <p className="text-sm text-muted-foreground">{item.description}</p> : null}
            <div className="flex flex-wrap items-center gap-2">
              {price ? (
                <p className="text-lg font-medium">
                  Selling Price {price}
                </p>
              ) : null}
              {original && original !== price ? <p className="text-sm text-muted-foreground">MRP {original}</p> : null}
              {discount ? <p className="text-sm text-muted-foreground">Discount {discount}</p> : null}
            </div>
            {isBestseller(item) ? <p className="text-sm">Best Seller</p> : null}
            {isCustomizable(item) ? <p className="text-sm">Customisable</p> : null}
            {availability ? <p className="text-sm text-muted-foreground">{availability}</p> : null}
            <GroupList title="Variants" groups={variants} />
            {customizations.length ? (
              <div className="space-y-2">
                <h3 className="text-sm font-medium">Customizations</h3>
                {customizations.map((group, groupIndex) => (
                  <div key={`${item.key}-custom-${group.name}-${groupIndex}`}>
                    <p className="text-sm text-muted-foreground">{group.name}</p>
                    <ul className="mt-1 space-y-1 text-sm">
                      {group.options.map((option) => {
                        const extra = { name: option.name, amount: option.amount };
                        const checked = selected.some((entry) => entry.name === option.name);
                        return (
                          <li key={`${item.key}-${group.name}-${option.id}`}>
                            <label className="flex cursor-pointer items-center justify-between gap-3">
                              <span>
                                {option.name}
                                {option.price ? ` · ${option.price}` : ""}
                              </span>
                              <input type="checkbox" checked={checked} onChange={() => toggleExtra(extra)} />
                            </label>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
        <div className="border-t border-border p-4">
          {extraCost > 0 ? <p className="mb-2 text-sm text-muted-foreground">Total {formatPrice(total)}</p> : null}
          <Button
            type="button"
            className="w-full"
            onClick={() => {
              onAdd(selected);
              onClose();
            }}
          >
            Add to Cart
          </Button>
        </div>
      </aside>
    </div>
  );
}

function GroupList({
  title,
  groups,
}: {
  title: string;
  groups: ReturnType<typeof variantGroups>;
}) {
  if (!groups.length) {
    return null;
  }
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{title}</h3>
      {groups.map((group, groupIndex) => (
        <div key={`${title}-${group.name}-${groupIndex}`}>
          <p className="text-sm text-muted-foreground">{group.name}</p>
          {group.options.length ? (
            <ul className="mt-1 space-y-0.5 text-sm">
              {group.options.map((option, optionIndex) => (
                <li key={`${title}-${groupIndex}-${option.name}-${optionIndex}`}>
                  {option.name}
                  {option.price ? ` · ${option.price}` : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function CartPanel({
  lines,
  onQuantity,
  onRemove,
}: {
  lines: CartLine[];
  onQuantity: (id: string, quantity: number) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <section className="rounded-lg border border-border bg-card p-4" aria-label="Your cart">
      <h2 className="mb-3 text-sm font-medium">Cart</h2>
      <ul className="space-y-3">
        {lines.map((line) => (
          <li key={line.id} className="space-y-1 text-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium">{line.name}</p>
                <p className="text-muted-foreground">{formatPrice(lineUnitTotal(line))}</p>
                {line.extras.map((extra) => (
                  <p key={`${line.id}-${extra.name}`} className="text-muted-foreground">
                    {extra.name} {extra.amount ? formatPrice(extra.amount) : ""}
                  </p>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <button type="button" aria-label={`Decrease ${line.name}`} onClick={() => onQuantity(line.id, line.quantity - 1)}>
                  <MinusIcon />
                </button>
                <span>{line.quantity}</span>
                <button type="button" aria-label={`Increase ${line.name}`} onClick={() => onQuantity(line.id, line.quantity + 1)}>
                  <PlusIcon />
                </button>
                <button type="button" className="text-muted-foreground" onClick={() => onRemove(line.id)}>
                  Remove
                </button>
              </div>
            </div>
            <p className="text-muted-foreground">Subtotal {formatPrice(lineSubtotal(line))}</p>
          </li>
        ))}
      </ul>
      <p className="mt-4 font-medium">Total {formatPrice(cartTotal(lines))}</p>
    </section>
  );
}
