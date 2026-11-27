import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

const SHEET = [
  "name,sku,unit,case_size,price",
  "Muscadet Domaine de l'Ecu,W-MUS-01,750ml bottle,12,19.50",
  "Chateau Nowhere 2015,,750ml bottle,12,30.00",
].join("\n");

test("upload a CSV price sheet, review it, and apply the matched offer", async ({ page }) => {
  await page.goto("/suppliers");
  await expect(page.getByRole("heading", { level: 1, name: "Supplier tastings" })).toBeVisible();
  const picker = page.getByTestId("supplier-picker");
  await expect(picker.locator("option", { hasText: "Kermit Lynch Wine Merchant" })).toHaveCount(1);
  await picker.selectOption({ label: "Kermit Lynch Wine Merchant" });

  await page.getByTestId("price-sheet-file").setInputFiles({
    name: "kermit-prices.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(SHEET),
  });
  const upload = page.getByTestId("price-sheet-upload");
  const uploadBox = await upload.boundingBox();
  expect(uploadBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await upload.click();

  const review = page.getByTestId("price-sheet-review");
  await expect(review).toBeVisible();
  await expect(review.getByTestId("price-sheet-row").filter({ hasText: "Muscadet" })).toContainText("matched");
  await expect(review.getByTestId("price-sheet-row").filter({ hasText: "Chateau Nowhere" })).toContainText("unmatched");
  await expect(review.getByText("USD 19.50")).toBeVisible();

  const apply = page.getByTestId("price-sheet-apply");
  const applyBox = await apply.boundingBox();
  expect(applyBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await apply.click();

  await expect(page.getByTestId("supplier-offer").filter({ hasText: "Muscadet" })).toContainText("USD 19.50");
  await expect(page.getByTestId("price-history")).toContainText("Muscadet");
  await expect(page.getByTestId("price-history-row").filter({ hasText: "offer" })).toContainText("USD 19.50");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
