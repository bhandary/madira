import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const OUT = "/opt/cursor/artifacts";

test.use({ video: "on", viewport: { width: 1440, height: 900 } });

test("capture key states for walkthrough artifacts", async ({ page }) => {
  fs.mkdirSync(path.join(OUT, "screenshots"), { recursive: true });

  await page.goto("/");
  await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);
  await page.screenshot({ path: path.join(OUT, "screenshots", "floor_home_wine_ui.png"), fullPage: true });

  await page.goto("/menu");
  await page.getByTestId("menu-file").setInputFiles(path.join(__dirname, "../../fixtures/sample_menu.txt"));
  await page.getByTestId("menu-workbench-submit").click();
  await expect(page.getByTestId("pairing-grid")).toBeVisible({ timeout: 90_000 });
  await page.screenshot({ path: path.join(OUT, "screenshots", "menu_pairings_a2ui_cards.png"), fullPage: true });

  await page.goto("/list");
  await page.getByTestId("list-budget").fill("12000");
  await page.getByTestId("list-margin").fill("3.2");
  await page.getByTestId("list-workbench-submit").click();
  await expect(page.getByTestId("beverage-list-table")).toBeVisible({ timeout: 90_000 });
  await page.screenshot({ path: path.join(OUT, "screenshots", "list_curation_budget_table.png"), fullPage: true });

  await page.goto("/inventory");
  await page.getByTestId("inv-sku").fill("W-MUS-01");
  await page.getByTestId("inv-qty").fill("1");
  await page.getByTestId("inv-adjust").click();
  await page.getByTestId("inventory-workbench-submit").click();
  await expect(page.getByTestId("purchase-order-table")).toBeVisible({ timeout: 90_000 });
  await page.screenshot({ path: path.join(OUT, "screenshots", "inventory_reorder_draft.png"), fullPage: true });

  await page.goto("/training");
  await page.getByTestId("training-quiz").click();
  await page.getByTestId("training-workbench-submit").click();
  await expect(page.getByTestId("quiz-score")).toBeVisible({ timeout: 90_000 });
  await page.screenshot({ path: path.join(OUT, "screenshots", "training_quiz_score.png"), fullPage: true });

  await page.goto("/suppliers");
  await page.getByTestId("suppliers-workbench-submit").click();
  await expect(page.getByTestId("ics-block")).toContainText("BEGIN:VCALENDAR");
  await page.screenshot({ path: path.join(OUT, "screenshots", "supplier_tasting_ics_draft.png"), fullPage: true });
});
