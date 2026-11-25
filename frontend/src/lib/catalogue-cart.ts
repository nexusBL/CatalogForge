export type CartExtra = {
  name: string;
  amount: number;
};

export type CartLine = {
  id: string;
  itemKey: string;
  name: string;
  unitPrice: number;
  quantity: number;
  extras: CartExtra[];
};

export function extrasTotal(extras: CartExtra[]): number {
  return extras.reduce((total, extra) => total + extra.amount, 0);
}

export function lineUnitTotal(line: CartLine): number {
  return line.unitPrice + extrasTotal(line.extras);
}

export function lineSubtotal(line: CartLine): number {
  return lineUnitTotal(line) * line.quantity;
}

export function cartTotal(lines: CartLine[]): number {
  return lines.reduce((total, line) => total + lineSubtotal(line), 0);
}

export function cartLineSignature(itemKey: string, extras: CartExtra[]): string {
  const extraKey = extras
    .map((extra) => extra.name)
    .sort()
    .join("|");
  return `${itemKey}::${extraKey}`;
}

export function addCartLine(lines: CartLine[], incoming: Omit<CartLine, "id" | "quantity"> & { quantity?: number }): CartLine[] {
  const signature = cartLineSignature(incoming.itemKey, incoming.extras);
  const quantity = incoming.quantity ?? 1;
  const existing = lines.find((line) => cartLineSignature(line.itemKey, line.extras) === signature);
  if (existing) {
    return lines.map((line) => (line.id === existing.id ? { ...line, quantity: line.quantity + quantity } : line));
  }
  return [...lines, { ...incoming, id: signature, quantity }];
}

export function setCartQuantity(lines: CartLine[], lineId: string, quantity: number): CartLine[] {
  if (quantity <= 0) {
    return lines.filter((line) => line.id !== lineId);
  }
  return lines.map((line) => (line.id === lineId ? { ...line, quantity } : line));
}

export function removeCartLine(lines: CartLine[], lineId: string): CartLine[] {
  return lines.filter((line) => line.id !== lineId);
}
