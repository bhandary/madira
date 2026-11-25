import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("demo POS maps a sale and the cellar on-hand drops", async ({ page }) => {
  await page.goto("/pos");
  await expect(page.getByRole("heading", { level: 1, name: "POS" })).toBeVisible();
  const connect = page.getByTestId("pos-connect");
  const connected = page.getByTestId("pos-connected");
  await expect(connect.or(connected)).toBeVisible();
  if (await connect.isVisible()) {
    await expect(connect).toBeEnabled();
    await Promise.all([
      page.waitForResponse((response) => response.request().method() === "POST" && response.url().includes("/pos/connect/demo") && response.ok()),
      connect.click(),
    ]);
  }
  await expect(connected).toBeVisible();

  const row = page.locator('[data-testid="pos-item"][data-variation="demo-var-muscadet"]');
  const save = row.getByRole("button", { name: "Save mapping" });
  await expect(save).toBeEnabled();
  await Promise.all([
    page.waitForResponse((response) => response.url().includes("/pos/mappings") && response.ok()),
    save.click(),
  ]);

  await page.goto("/inventory");
  const stock = page.locator('[data-testid="sku-row"][data-sku="W-MUS-01"]');
  await expect(stock.getByTestId("sku-on-hand")).toBeVisible();
  const before = Number(await stock.getByTestId("sku-on-hand").innerText());

  await page.goto("/pos");
  const sync = page.getByTestId("pos-sync");
  await expect(sync).toBeEnabled();
  const targets = await page.locator('[data-testid="pos-sync"], [data-testid="pos-item"] button').evaluateAll((nodes) =>
    nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    }),
  );
  expect(targets.length).toBeGreaterThan(0);
  for (const target of targets) {
    expect(target.height).toBeGreaterThanOrEqual(44);
    expect(target.width).toBeGreaterThanOrEqual(44);
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  await Promise.all([
    page.waitForResponse((response) => response.request().method() === "POST" && response.url().includes("/pos/sync") && response.ok()),
    sync.click(),
  ]);
  await expect(page.getByTestId("pos-run").first()).toContainText(/posted/i);

  await page.goto("/inventory");
  await expect(stock.getByTestId("sku-on-hand")).toHaveText(String(before - 1));
});
