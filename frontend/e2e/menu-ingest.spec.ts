import path from "node:path";
import { expect, test } from "@playwright/test";

test("reads a menu photo, edits a flagged field, and confirms it on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/menu");
  await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);
  await expect(page.getByTestId("mode-banner")).not.toContainText(/connecting/i);
  await expect(page.getByRole("heading", { level: 1, name: "Menu & pairings" })).toBeVisible();

  const photo = path.join(__dirname, "../../fixtures/sample_menu.png");
  await page.getByTestId("menu-camera").setInputFiles(photo);
  await expect(page.getByTestId("menu-camera")).toHaveAttribute("accept", "image/*;capture");
  await page.getByTestId("menu-ingest-submit").click();

  await expect(page.getByTestId("dish-review")).toBeVisible();
  await expect(page.getByTestId("dish-review-status")).toHaveText("Draft");
  await expect(page.getByTestId("dish-name").first()).toContainText("Dungeness crab");
  await expect(page.getByTestId("dish-flag").first()).toBeVisible();

  const sauce = page.getByTestId("dish-field-sauce");
  await expect(sauce).toHaveValue("yuzu");
  await sauce.fill("yuzu kosho");
  await page.getByTestId("dish-save").click();
  await expect(page.getByTestId("dish-value-sauce").first()).toContainText("yuzu kosho");

  await page.getByTestId("dish-confirm").click();
  await expect(page.getByTestId("dish-review-status")).toHaveText("Confirmed");
  await expect(page.getByTestId("dish-value-sauce").first()).toContainText("yuzu kosho");

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});
