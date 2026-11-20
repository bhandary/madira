import path from "node:path";
import { expect, test } from "@playwright/test";

test("pins, swaps, and rejects a pairing on a phone, then keeps them", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto("/list");
  await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);
  await expect(page.getByTestId("mode-banner")).not.toContainText(/connecting/i);
  const csvPath = path.join(__dirname, "../../fixtures/sample_list.csv");
  await page.getByTestId("list-import-file").setInputFiles(csvPath);
  await page.getByTestId("list-import-preview").click();
  await page.getByTestId("list-import-confirm").click();
  await expect(page.getByTestId("list-import-entries")).toContainText("Chablis");

  const menusReady = page.waitForResponse(
    (res) => res.url().includes("/madira-api/menus") && res.request().method() === "GET" && res.ok(),
  );
  await page.goto("/menu");
  await menusReady;
  await expect(page.getByRole("heading", { level: 1, name: "Menu & pairings" })).toBeVisible();
  const menuPath = path.join(__dirname, "../../fixtures/sample_menu.txt");
  await page.getByTestId("menu-ingest-file").setInputFiles(menuPath);
  await page.getByTestId("menu-ingest-submit").click();
  await expect(page.getByTestId("dish-review")).toBeVisible();
  await page.getByTestId("dish-confirm").click();
  await expect(page.getByTestId("dish-review-status")).toHaveText("Confirmed");
  await page.getByTestId("menu-pair").click();

  const grid = page.getByTestId("menu-ingest").getByTestId("pairing-grid");
  await expect(grid).toBeVisible();
  const card = grid.getByTestId("pairing-card").first();
  await expect(card.getByTestId("pairing-slot-best_by_the_glass")).toBeVisible();
  await expect(card.getByTestId("pairing-slot-best_bottle")).toBeVisible();
  await expect(card.getByTestId("pairing-slot-value")).toBeVisible();
  await expect(card.getByTestId("pairing-slot-adventurous")).toBeVisible();

  const glass = card.getByTestId("pairing-slot-best_by_the_glass");
  const glassName = (await glass.getByTestId("pairing-name").innerText()).trim();
  await glass.getByTestId("pairing-pin").click();
  await expect(glass.getByTestId("pairing-status")).toHaveText("Pinned");

  const bottle = card.getByTestId("pairing-slot-best_bottle");
  const bottleName = (await bottle.getByTestId("pairing-name").innerText()).trim();
  await bottle.getByTestId("pairing-swap-select").selectOption({ index: 1 });
  await bottle.getByTestId("pairing-swap").click();
  await expect(bottle.getByTestId("pairing-status")).toHaveText("Swapped");
  const swappedName = (await bottle.getByTestId("pairing-name").innerText()).trim();
  expect(swappedName).not.toBe(bottleName);

  const value = card.getByTestId("pairing-slot-value");
  const valueName = (await value.getByTestId("pairing-name").innerText()).trim();
  await value.getByTestId("pairing-reject").click();
  await expect(value.getByTestId("pairing-status")).toHaveText("Rejected");
  await expect(value.getByTestId("pairing-name")).toHaveText(valueName);

  await page.reload();
  const keptGrid = page.getByTestId("menu-ingest").getByTestId("pairing-grid");
  await expect(keptGrid).toBeVisible();
  const kept = keptGrid.getByTestId("pairing-card").first();
  await expect(kept.getByTestId("pairing-slot-best_by_the_glass").getByTestId("pairing-status")).toHaveText("Pinned");
  await expect(kept.getByTestId("pairing-slot-best_by_the_glass").getByTestId("pairing-name")).toHaveText(glassName);
  await expect(kept.getByTestId("pairing-slot-best_bottle").getByTestId("pairing-status")).toHaveText("Swapped");
  await expect(kept.getByTestId("pairing-slot-best_bottle").getByTestId("pairing-name")).toHaveText(swappedName);
  await expect(kept.getByTestId("pairing-slot-value").getByTestId("pairing-status")).toHaveText("Rejected");
  await expect(kept.getByTestId("pairing-slot-value").getByTestId("pairing-name")).toHaveText(valueName);

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});
