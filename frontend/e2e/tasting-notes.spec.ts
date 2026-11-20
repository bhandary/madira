import path from "node:path";
import { expect, test } from "@playwright/test";

test("drafts, edits, and approves a tasting note on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/list");
  await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);
  await expect(page.getByTestId("mode-banner")).not.toContainText(/connecting/i);
  await expect(page.getByRole("heading", { level: 1, name: "List curation" })).toBeVisible();

  const csvPath = path.join(__dirname, "../../fixtures/sample_list.csv");
  await page.getByTestId("list-import-file").setInputFiles(csvPath);
  await page.getByTestId("list-import-preview").click();
  await expect(page.getByTestId("list-import-summary")).toContainText(/\d+ matched/);
  await page.getByTestId("list-import-confirm").click();
  await expect(page.getByTestId("list-import-entries")).toContainText("Chablis Premier Cru Vaillons");

  await page.getByRole("button", { name: "Notes for Chablis Premier Cru Vaillons" }).click();
  const panel = page.getByTestId("tasting-notes");
  await expect(panel).toBeVisible();
  await page.getByTestId("tasting-note-draft").click();

  await expect(page.getByTestId("tasting-note-card")).toBeVisible();
  await expect(page.getByTestId("tasting-note-status")).toHaveText("Draft");
  await expect(page.getByTestId("tasting-note-hook")).toContainText("Chablis Premier Cru Vaillons");
  await expect(page.getByTestId("service-card")).toBeVisible();
  await expect(page.getByTestId("service-card-status")).toHaveText("Draft");
  await expect(page.getByTestId("service-card-glassware")).toHaveText("White wine glass");

  await page.getByTestId("tasting-note-edit").click();
  const hook = page.getByTestId("tasting-note-hook-input");
  await hook.fill("Crisp and ready for oysters.");
  await page.getByTestId("tasting-note-save").click();
  await expect(page.getByTestId("tasting-note-hook")).toHaveText("Crisp and ready for oysters.");
  await expect(page.getByTestId("tasting-note-status")).toHaveText("Draft");

  await page.getByTestId("tasting-note-approve").click();
  await expect(page.getByTestId("tasting-note-status")).toHaveText("Approved");
  await expect(page.getByTestId("tasting-note-hook")).toHaveText("Crisp and ready for oysters.");

  await page.getByTestId("service-card-approve").click();
  await expect(page.getByTestId("service-card-status")).toHaveText("Approved");
  await expect(page.getByTestId("service-card-temperature")).toHaveText("45-50°F");

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});
