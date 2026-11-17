import path from "node:path";
import { expect, test } from "@playwright/test";

test("imports the sample list on a phone and shows the entries", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/list");
  await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);
  await expect(page.getByTestId("mode-banner")).not.toContainText(/connecting/i);
  await expect(page.getByRole("heading", { level: 1, name: "List curation" })).toBeVisible();

  const csvPath = path.join(__dirname, "../../fixtures/sample_list.csv");
  await page.getByTestId("list-import-file").setInputFiles(csvPath);
  await page.getByTestId("list-import-preview").click();

  const summary = page.getByTestId("list-import-summary");
  await expect(summary).toContainText(/\d+ matched/);
  await expect(summary).toContainText(/\d+ new products/);
  await expect(summary).toContainText(/\d+ errors/);
  const preview = page.getByTestId("list-import-preview-table");
  await expect(preview).toContainText("Muscadet Domaine de l'Ecu");
  await expect(preview).toContainText("Matched");
  await expect(preview).toContainText("Chablis Premier Cru Vaillons");

  await page.getByTestId("list-import-confirm").click();
  const entries = page.getByTestId("list-import-entries");
  await expect(entries).toBeVisible();
  await expect(entries).toContainText("Chablis Premier Cru Vaillons");
  await expect(entries).toContainText("Barolo");
  await expect(entries).toContainText("Kölsch");
  await expect(entries).toContainText("Dassai 45");
  await expect(entries).toContainText("By the glass");

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});
