/** Deterministic floor-lookup parser. A port of madira.domain.training.lookup.parse_query. */

import type { LookupFilters } from "@/lib/api-types.gen";

export type { LookupFilters };

const DOLLARS = /\bunder\s+(\d+(?:\.\d+)?)\s+dollars?\b/i;
const PRICE = /\bunder\s*\$?\s*(\d+(?:\.\d+)?)\b/i;

const GRAPES = [
  "sauvignon blanc",
  "cabernet sauvignon",
  "pinot noir",
  "pinot grigio",
  "pinot gris",
  "chenin blanc",
  "chardonnay",
  "riesling",
  "nebbiolo",
  "sangiovese",
  "tempranillo",
  "grenache",
  "mourvedre",
  "viognier",
  "albarino",
  "albariño",
  "gamay",
  "syrah",
  "shiraz",
  "merlot",
  "cabernet",
  "chenin",
] as const;

const STYLES: readonly [string, keyof LookupFilters, readonly string[]][] = [
  ["full-bodied", "body", ["full"]],
  ["full bodied", "body", ["full"]],
  ["light-bodied", "body", ["light"]],
  ["light bodied", "body", ["light"]],
  ["bone-dry", "sweetness", ["bone-dry"]],
  ["off-dry", "sweetness", ["off-dry"]],
  ["unoaked", "oak", ["none"]],
  ["oaky", "oak", ["light", "medium", "heavy"]],
  ["oaked", "oak", ["light", "medium", "heavy"]],
  ["tannic", "tannin", ["medium", "high"]],
  ["crisp", "acidity", ["high"]],
  ["bright", "acidity", ["high", "medium"]],
  ["sweet", "sweetness", ["sweet", "medium-sweet"]],
  ["dry", "sweetness", ["bone-dry", "dry"]],
];

function emptyFilters(maxPrice: number | null): LookupFilters {
  return {
    text: "",
    grape: "",
    producer: "",
    region: "",
    dish: "",
    style: "",
    max_price_cents: maxPrice,
    body: [],
    acidity: [],
    tannin: [],
    sweetness: [],
    oak: [],
    intensity: [],
  };
}

function isWord(char: string | undefined): boolean {
  if (!char) return false;
  return /[\p{L}\p{N}_]/u.test(char);
}

function isBoundary(text: string, index: number): boolean {
  const before = index > 0 && isWord(text[index - 1]);
  const after = index < text.length && isWord(text[index]);
  return before !== after;
}

function findBounded(text: string, phrase: string): number {
  let from = 0;
  while (from <= text.length - phrase.length) {
    const index = text.indexOf(phrase, from);
    if (index < 0) return -1;
    if (isBoundary(text, index) && isBoundary(text, index + phrase.length)) return index;
    from = index + 1;
  }
  return -1;
}

function replaceBounded(text: string, phrase: string): { found: boolean; text: string } {
  let found = false;
  let cursor = 0;
  let out = "";
  while (cursor < text.length) {
    const slice = text.slice(cursor);
    const index = findBounded(slice, phrase);
    if (index < 0) {
      out += slice;
      break;
    }
    found = true;
    out += `${slice.slice(0, index)} `;
    cursor += index + phrase.length;
  }
  return { found, text: out };
}

function collapse(value: string): string {
  return value.split(/\s+/).filter(Boolean).join(" ");
}

function capitalize(word: string): string {
  if (!word) return word;
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
}

/** ROUND_HALF_UP cents, matching Decimal(dollars) * 100 quantized to an integer. */
export function dollarsToCents(raw: string): number {
  const [wholeRaw, fracRaw = ""] = raw.split(".");
  const whole = Number(wholeRaw || "0");
  const centsPart = Number((fracRaw + "00").slice(0, 2));
  const roundDigit = Number((fracRaw + "000")[2] || "0");
  return whole * 100 + centsPart + (roundDigit >= 5 ? 1 : 0);
}

export function parseQuery(query: string): LookupFilters {
  let raw = (query || "").trim();
  let maxPrice: number | null = null;
  const match = DOLLARS.exec(raw) || PRICE.exec(raw);
  if (match && match.index !== undefined) {
    maxPrice = dollarsToCents(match[1]);
    raw = `${raw.slice(0, match.index)} ${raw.slice(match.index + match[0].length)}`;
  }
  let lowered = collapse(raw.toLowerCase());
  const filters = emptyFilters(maxPrice);
  for (const [phrase, field, values] of STYLES) {
    const replaced = replaceBounded(lowered, phrase);
    if (!replaced.found) continue;
    if (field === "body" || field === "acidity" || field === "tannin" || field === "sweetness" || field === "oak" || field === "intensity") {
      filters[field] = [...values];
    }
    lowered = replaced.text;
  }
  for (const grape of GRAPES) {
    const index = findBounded(lowered, grape);
    if (index < 0) continue;
    filters.grape = grape.split(" ").map(capitalize).join(" ");
    lowered = `${lowered.slice(0, index)} ${lowered.slice(index + grape.length)}`;
    break;
  }
  filters.text = collapse(lowered);
  return filters;
}

export function parserResultId(filters: LookupFilters): string {
  const payload = {
    acidity: filters.acidity,
    body: filters.body,
    dish: filters.dish,
    grape: filters.grape,
    intensity: filters.intensity,
    max_price_cents: filters.max_price_cents,
    oak: filters.oak,
    producer: filters.producer,
    region: filters.region,
    style: filters.style,
    sweetness: filters.sweetness,
    tannin: filters.tannin,
    text: filters.text,
  };
  return JSON.stringify(payload);
}
