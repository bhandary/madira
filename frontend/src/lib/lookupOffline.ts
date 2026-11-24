/** Offline floor lookup over the cached pack. Filtering follows the backend lookup. */

import type { LookupHit } from "@/lib/api";
import { parseQuery, type LookupFilters } from "@/lib/lookupParse";

export type PackItem = {
  id: string;
  product_id: string;
  sku: string;
  name: string;
  producer: string;
  grape: string;
  region: string;
  style: string;
  category: string;
  body: string;
  acidity: string;
  tannin: string;
  sweetness: string;
  oak: string;
  intensity: string;
  on_list: boolean;
  price_cents: number;
  currency: string;
  stock: number;
  eighty_six: boolean;
};

export type PackNote = {
  id: string;
  product_id: string;
  server_hook: string;
  guest_description: string;
  body: string;
  acidity: string;
  tannin: string;
  sweetness: string;
  oak: string;
  intensity: string;
};

export type PackCard = {
  id: string;
  product_id: string;
  glassware: string;
  serving_temperature: string;
  pour_size: string;
  decanting: string;
};

export type PackDish = {
  id: string;
  name: string;
  description: string;
  course: string;
};

export type PackPairing = {
  id: string;
  sku_id: string;
  dish_id: string;
  dish: string;
  course: string;
  description: string;
  script: string;
  pinned: boolean;
};

export type LookupPack = {
  service_date: string;
  items: PackItem[];
  notes: PackNote[];
  cards: PackCard[];
  dishes: PackDish[];
  pairings: PackPairing[];
};

function contains(hay: string, needle: string): boolean {
  if (!needle) return true;
  return (hay || "").toLowerCase().includes(needle.toLowerCase());
}

function level(value: string, allowed: string[]): boolean {
  if (!allowed.length) return true;
  return allowed.includes((value || "").trim().toLowerCase());
}

function filled(primary: string, fallback: string): string {
  if ((primary || "").trim()) return primary;
  return fallback || "";
}

function profileWords(note: PackNote): string {
  if ((note.guest_description || "").trim()) return note.guest_description.trim();
  const bits = [
    note.body && `${note.body} body`,
    note.acidity && `${note.acidity} acidity`,
    note.tannin && `${note.tannin} tannin`,
    note.sweetness,
    note.oak && `${note.oak} oak`,
  ];
  return bits.filter(Boolean).join(", ");
}

export function searchPack(pack: LookupPack, query: string): LookupHit[] {
  const filters: LookupFilters = parseQuery(query);
  const noteByProduct = new Map<string, PackNote>();
  for (const note of pack.notes || []) {
    if (!noteByProduct.has(note.product_id)) noteByProduct.set(note.product_id, note);
  }
  const cardByProduct = new Map<string, PackCard>();
  for (const card of pack.cards || []) {
    if (!cardByProduct.has(card.product_id)) cardByProduct.set(card.product_id, card);
  }
  const text = filters.text.trim();
  const dishNeedles = filters.dish.trim() ? [filters.dish.trim()] : [];
  if (text) dishNeedles.push(text);
  const dishIds = new Set<string>();
  for (const dish of pack.dishes || []) {
    const blob = `${dish.name} ${dish.description} ${dish.course}`;
    if (dishNeedles.some((needle) => needle && contains(blob, needle))) dishIds.add(dish.id);
  }
  const pairings = pack.pairings || [];
  const results: LookupHit[] = [];
  const seen = new Set<string>();
  for (const item of pack.items || []) {
    const note = noteByProduct.get(item.product_id);
    if (!note) continue;
    if (filters.grape && !(contains(item.grape, filters.grape) || contains(item.style, filters.grape) || contains(item.name, filters.grape))) {
      continue;
    }
    if (filters.producer && !contains(item.producer, filters.producer)) continue;
    if (filters.region && !contains(item.region, filters.region)) continue;
    if (filters.style && !contains(item.style, filters.style)) continue;
    if (!level(filled(note.oak, item.oak), filters.oak)) continue;
    if (!level(filled(note.body, item.body), filters.body)) continue;
    if (!level(filled(note.acidity, item.acidity), filters.acidity)) continue;
    if (!level(filled(note.tannin, item.tannin), filters.tannin)) continue;
    if (!level(filled(note.sweetness, item.sweetness), filters.sweetness)) continue;
    if (!level(filled(note.intensity, item.intensity), filters.intensity)) continue;
    const price = item.price_cents;
    if (filters.max_price_cents != null && (price <= 0 || price >= filters.max_price_cents)) continue;
    let related = pairings.filter((row) => row.sku_id === item.id);
    if (dishIds.size) {
      related = related.filter((row) => dishIds.has(row.dish_id));
      const wineBlob = `${item.name} ${item.producer} ${item.region} ${item.grape} ${item.style}`;
      if (!related.length && text && !contains(wineBlob, text)) continue;
    }
    const textBlob = [item.name, item.producer, item.region, item.grape, item.style, note.guest_description || "", note.server_hook || ""].join(" ");
    const named = Boolean(text) && contains(textBlob, text);
    if (text && !named && !related.length) continue;
    if (
      !text &&
      !filters.grape &&
      !filters.producer &&
      !filters.region &&
      !filters.oak.length &&
      !filters.body.length &&
      !filters.acidity.length &&
      !filters.tannin.length &&
      !filters.sweetness.length &&
      !filters.intensity.length &&
      !dishIds.size
    ) {
      continue;
    }
    const pinned = related.find((row) => row.pinned && (row.script || "").trim());
    const chosen = pinned || related.find((row) => (row.script || "").trim());
    const script = chosen ? (chosen.script || "").trim() : (note.server_hook || "").trim();
    const pairingName = chosen ? chosen.dish : "";
    const key = `${item.id}:${pairingName}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const card = cardByProduct.get(item.product_id);
    results.push({
      name: item.name,
      producer: item.producer,
      grape: item.grape,
      region: item.region,
      pairing: pairingName,
      server_script: script,
      flavor_profile: profileWords(note),
      glassware: card ? card.glassware : "",
      serving_temperature: card ? card.serving_temperature : "",
      pour_size: card ? card.pour_size : "",
      stock: item.stock,
      price_cents: price,
      currency: item.currency || "USD",
    });
  }
  results.sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()) || a.pairing.toLowerCase().localeCompare(b.pairing.toLowerCase()));
  return results;
}
