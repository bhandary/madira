import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("usage limits and an auditor table fit a phone", async ({ page }) => {
  await page.goto("/usage");
  await expect(page.getByRole("heading", { level: 1, name: "Usage" })).toBeVisible();
  const save = page.getByTestId("usage-save");
  await expect(save).toBeEnabled();
  await expect(page.getByTestId("usage-spent")).toContainText(/spent \d+ cents/);
  await page.getByTestId("usage-cap").fill("500");
  await page.getByTestId("usage-rpm").fill("30");
  await Promise.all([
    page.waitForResponse((response) => response.url().includes("/usage/limits") && response.request().method() === "PUT" && response.ok()),
    save.click(),
  ]);
  await expect(page.getByTestId("usage-cap-status")).toContainText("Cap 500 cents");
  await expect(page.getByTestId("usage-cap-status")).toContainText("Limit 30 requests per minute");
  const targets = await page.locator('[data-testid="usage-save"], [data-testid="usage-cap"], [data-testid="usage-rpm"]').evaluateAll((nodes) =>
    nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    }),
  );
  expect(targets.length).toBe(3);
  for (const target of targets) {
    expect(target.height).toBeGreaterThanOrEqual(44);
    expect(target.width).toBeGreaterThanOrEqual(44);
  }
  const usageOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(usageOverflow).toBeLessThanOrEqual(1);

  await page.goto("/audit");
  await expect(page.getByRole("heading", { level: 1, name: "Audit" })).toBeVisible();
  await expect(page.getByTestId("auditor-row").first()).toBeVisible();
  const link = page.getByTestId("auditor-link").first();
  await expect(link).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await link.click();
  await expect(page).toHaveURL(/\/inventory/);
  await expect(page.getByRole("heading", { level: 1, name: "Inventory & purchasing" })).toBeVisible();
});
