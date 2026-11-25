import { describe, expect, it } from "vitest";
import { addCartLine, cartTotal, removeCartLine, setCartQuantity, type CartLine } from "@/lib/catalogue-cart";

const naan: Omit<CartLine, "id" | "quantity"> = {
  itemKey: "item-naan-1",
  name: "Butter Naan",
  unitPrice: 70,
  extras: [],
};

describe("catalogue cart", () => {
  it("adds a product and increases quantity for the same configuration", () => {
    const once = addCartLine([], naan);
    const twice = addCartLine(once, naan);
    expect(twice).toHaveLength(1);
    expect(twice[0].quantity).toBe(2);
    expect(cartTotal(twice)).toBe(140);
  });

  it("treats a different customization as a separate line", () => {
    const base = addCartLine([], naan);
    const withCheese = addCartLine(base, { ...naan, extras: [{ name: "Extra Cheese", amount: 65 }] });
    expect(withCheese).toHaveLength(2);
    expect(cartTotal(withCheese)).toBe(205);
  });

  it("increases, decreases, and removes lines", () => {
    const added = addCartLine([], { ...naan, extras: [{ name: "Butter", amount: 10 }] });
    const more = setCartQuantity(added, added[0].id, 3);
    expect(cartTotal(more)).toBe(240);
    const less = setCartQuantity(more, added[0].id, 1);
    expect(less[0].quantity).toBe(1);
    expect(removeCartLine(less, added[0].id)).toEqual([]);
  });

  it("totals multiple products", () => {
    const lines = addCartLine(addCartLine([], naan), {
      itemKey: "item-tikka-1",
      name: "Chicken Tikka",
      unitPrice: 249,
      extras: [],
    });
    const qty = setCartQuantity(lines, "item-tikka-1::", 2);
    expect(cartTotal(qty)).toBe(70 + 498);
  });
});
