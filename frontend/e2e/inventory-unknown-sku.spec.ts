import { expect, test } from "@playwright/test";

test("an unknown SKU shows the server error", async ({ page }) => {
  await page.goto("/inventory");
  await expect(page.getByTestId("mode-banner")).not.toContainText("connecting");
  await page.getByTestId("inv-sku").fill("NOPE-00");
  await page.getByTestId("inv-qty").fill("1");
  await page.getByTestId("inv-adjust").click();
  await expect(page.getByTestId("inventory-error")).toHaveText("unknown sku NOPE-00");
});
