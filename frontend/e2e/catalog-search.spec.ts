import { expect, test } from "@playwright/test";

test("catalog search finds Barolo by name", async ({ page }) => {
  await page.goto("/inventory");
  await expect(page.getByTestId("mode-banner")).not.toContainText(/connecting/i);
  await page.getByTestId("catalog-search").fill("Barolo");
  await page.getByTestId("catalog-search-submit").click();
  await expect(page.getByTestId("catalog-search-mode")).toHaveText("Ranked by taste similarity.");
  await expect(page.locator('[data-testid="catalog-hit"][data-name="Barolo G.D. Vajra 2019"]')).toBeVisible();
});
