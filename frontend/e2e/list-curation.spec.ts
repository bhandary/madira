import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("curate from the menu on a phone", async ({ page }) => {
  await page.goto("/list");
  await expect(page.getByRole("heading", { name: "List curation" })).toBeVisible();
  await page.getByTestId("list-budget").fill("12000");
  await page.getByTestId("list-margin").fill("3.2");
  await page.getByTestId("list-target-cost").fill("31.3");
  await page.getByTestId("list-curate").click();
  const editor = page.getByTestId("list-editor");
  await expect(editor).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("coverage-grid")).toBeVisible();
  await expect(page.getByTestId("list-health")).toBeVisible();
  await expect(page.getByTestId("list-section").first()).toBeVisible();
  const before = await editor.getByTestId("list-item").count();
  expect(before).toBeGreaterThan(0);
  await editor.getByTestId("list-item-remove").first().click();
  await expect(editor.getByTestId("list-item")).toHaveCount(before - 1);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  const height = await page.getByTestId("list-curate").evaluate((node) => node.getBoundingClientRect().height);
  expect(height).toBeGreaterThanOrEqual(44);
});
