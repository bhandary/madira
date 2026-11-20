import { expect, test } from "@playwright/test";
import path from "node:path";

test.describe.configure({ mode: "serial" });

test("demo banner is visible", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);
});

test("upload sample menu and get A2UI pairings", async ({ page }) => {
  await page.goto("/menu");
  const menuPath = path.join(__dirname, "../../fixtures/sample_menu.txt");
  await page.getByTestId("menu-file").setInputFiles(menuPath);
  await page.getByTestId("menu-workbench-submit").click();
  await expect(page.getByTestId("delegation-panel")).toBeVisible();
  await expect(page.getByTestId("delegate-menu-analyst")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("delegate-pairing-sommelier")).toBeVisible();
  await expect(page.getByTestId("a2ui-surface")).toBeVisible();
  const surface = page.getByTestId("agent-reply");
  await expect(surface.getByTestId("pairing-grid")).toBeVisible();
  await expect(surface.getByTestId("pairing-card").first()).toContainText(/crab|mousse|risotto|ribeye|chocolate/i);
  await expect(surface.getByTestId("pairing-slot-best_by_the_glass").first()).toBeVisible();
});

test("curate a list under a budget", async ({ page }) => {
  await page.goto("/list");
  await page.getByTestId("list-budget").fill("12000");
  await page.getByTestId("list-margin").fill("3.2");
  await page.getByTestId("list-workbench-submit").click();
  await expect(page.getByTestId("delegate-list-curator")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("beverage-list-table")).toBeVisible();
  await expect(page.getByTestId("list-summary")).toContainText(/Budget/i);
  await expect(page.getByTestId("list-summary")).toContainText("$12,000");
  await expect(page.getByTestId("list-summary")).toContainText("$5,198");
  await expect(page.getByTestId("list-summary")).toContainText("3.2x");
  await expect(page.getByTestId("beverage-list-table")).toContainText(/wine/i);
});

test("adjust inventory and draft a reorder", async ({ page }) => {
  await page.goto("/inventory");
  await page.getByTestId("inv-sku").fill("W-MUS-01");
  await page.getByTestId("inv-qty").fill("1");
  await page.getByTestId("inv-adjust").click();
  await page.getByTestId("inventory-workbench-submit").click();
  await expect(page.getByTestId("delegate-inventory-purchasing")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("purchase-order-table")).toBeVisible();
  await expect(page.getByTestId("purchase-order-table")).toContainText(/DRAFT/i);
});

test("take a training quiz", async ({ page }) => {
  await page.goto("/training");
  await page.getByTestId("training-quiz").click();
  await page.getByTestId("training-workbench-submit").click();
  await expect(page.getByTestId("delegate-staff-trainer")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("quiz-card")).toBeVisible();
  await expect(page.getByTestId("quiz-score")).toContainText(/Score/);
});

test("schedule a supplier tasting with ics draft", async ({ page }) => {
  await page.goto("/suppliers");
  await page.getByTestId("suppliers-workbench-submit").click();
  await expect(page.getByTestId("delegate-supplier-scheduler")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("tasting-calendar")).toBeVisible();
  await expect(page.getByTestId("ics-block")).toContainText("BEGIN:VCALENDAR");
  await expect(page.getByTestId("ics-block")).toContainText(/DTSTART:\d{8}T1500/);
  await expect(page.getByTestId("ics-block")).toContainText(/DTEND:\d{8}T1700/);
  await expect(page.getByTestId("schedule-form")).toContainText(/not sent/i);
});
