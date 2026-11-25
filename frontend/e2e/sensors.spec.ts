import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("a sensor CSV excursion and a reminder show on Tonight", async ({ page }) => {
  const external = `s${Date.now().toString(36)}`;
  await page.goto("/sensors");
  await expect(page.getByRole("heading", { level: 1, name: "Sensors" })).toBeVisible();
  const create = page.getByTestId("sensor-create");
  await expect(create).toBeEnabled();
  await page.getByLabel("Name").fill("Cellar probe");
  await page.getByTestId("sensor-zone").selectOption({ label: "Main Cellar" });
  await page.getByTestId("sensor-external").fill(external);
  await Promise.all([
    page.waitForResponse((response) => response.request().method() === "POST" && response.url().includes("/sensors") && response.ok()),
    create.click(),
  ]);
  await expect(page.getByTestId("sensor-secret")).toBeVisible();

  const at = new Date().toISOString();
  const csv = `sensor,timestamp,metric,value\n${external},${at},temperature_c,30\n`;
  await page.getByTestId("sensor-csv").setInputFiles({
    name: "readings.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  const preview = page.getByTestId("sensor-preview");
  await expect(preview).toBeEnabled();
  await Promise.all([
    page.waitForResponse((response) => response.url().includes("/sensors/imports") && response.request().method() === "POST" && response.ok()),
    preview.click(),
  ]);
  await expect(page.getByTestId("sensor-preview-row")).toContainText(/excursion/i);
  const apply = page.getByTestId("sensor-apply");
  await expect(apply).toBeEnabled();
  const targets = await page.locator('[data-testid="sensor-create"], [data-testid="sensor-preview"], [data-testid="sensor-apply"]').evaluateAll((nodes) =>
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
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await Promise.all([
    page.waitForResponse((response) => response.url().includes("/apply") && response.ok()),
    apply.click(),
  ]);

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Tonight" })).toBeVisible();
  await expect(page.getByTestId("tonight-storage-alert").filter({ hasText: "Main Cellar" }).first()).toBeVisible();
  await expect(page.getByTestId("tonight-reminder").filter({ hasText: "ABC license renewal" }).first()).toBeVisible();
});
