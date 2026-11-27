import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { parseQuery, parserResultId } from "../src/lib/lookupParse";

const vectors = JSON.parse(readFileSync(path.join(__dirname, "../../fixtures/lookup_vectors.json"), "utf8")) as {
  query: string;
  id: string;
  expect: Record<string, unknown>;
}[];

test("the client parser matches the shared lookup vectors", () => {
  expect(vectors.length).toBeGreaterThan(0);
  for (const row of vectors) {
    const filters = parseQuery(row.query);
    expect(parserResultId(filters)).toBe(row.id);
    expect(filters).toEqual(row.expect);
  }
});
