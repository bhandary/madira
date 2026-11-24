import { expect, test } from "@playwright/test";

function qtyOf(text: string | null) {
  const value = Number(text);
  if (!Number.isFinite(value)) throw new Error(`expected a quantity, got ${text}`);
  return value;
}

test("location filter, bin labels, movements, and transfers stay consistent", async ({ page }) => {
  await page.goto("/inventory");
  await expect(page.getByTestId("cellar-board")).toBeVisible();
  await expect(page.getByTestId("location-pill").first()).toContainText("All locations");

  const muscat = page.getByTestId("sku-row").filter({ hasText: "W-MUS-01" });
  await expect(muscat).toBeVisible();
  const cellarBefore = qtyOf(await muscat.getByTestId("location-qty").filter({ hasText: "Main Cellar" }).getAttribute("data-qty"));
  const onHandBefore = qtyOf(await muscat.getByTestId("sku-on-hand").textContent());

  await page.getByTestId("location-pill").filter({ hasText: "Main Cellar" }).click();
  const filtered = page.getByTestId("sku-row");
  await expect(filtered.first()).toBeVisible();
  const filteredCount = await filtered.count();
  for (let index = 0; index < filteredCount; index += 1) {
    const shown = await filtered.nth(index).getByTestId("location-qty").filter({ hasText: "Main Cellar" }).getAttribute("data-qty");
    expect(qtyOf(shown)).not.toBe(0);
  }
  await page.getByTestId("location-pill").filter({ hasText: "All locations" }).click();
  await expect(muscat).toBeVisible();

  await page.getByTestId("cellar-tab-places").click();
  const stamp = Date.now().toString(36).toUpperCase();
  const code = `E2E-${stamp}`;
  const reason = `Playwright delivery ${stamp}`;
  await page.getByTestId("bin-location").selectOption({ label: "Main Cellar" });
  await page.getByTestId("bin-code").fill(code);
  await page.getByTestId("bin-label").fill("Playwright bin");
  await page.getByTestId("bin-create").click();
  const created = page.getByTestId("bin-row").filter({ hasText: code });
  await expect(created).toBeVisible();
  await created.getByTestId("bin-view-qr").click();
  await expect(page.getByTestId("bin-qr").locator("svg")).toBeVisible();
  await expect(page.getByTestId("bin-qr-payload")).toContainText(`:${code}`);
  await expect(page.getByTestId("bin-qr-payload")).toContainText("madira:bin:");

  await page.getByTestId("cellar-tab-stock").click();
  await page.getByTestId("movement-sku").selectOption("W-MUS-01");
  await page.getByTestId("movement-type").selectOption("receive");
  await page.getByTestId("movement-qty").fill("1.5");
  await page.getByTestId("movement-location").selectOption({ label: "Main Cellar" });
  await page.getByTestId("movement-reason").fill(reason);
  await page.getByTestId("movement-submit").click();

  await expect.poll(async () => qtyOf(await muscat.getByTestId("sku-on-hand").textContent())).toBeCloseTo(onHandBefore + 1.5, 2);
  const cellarAfterReceive = qtyOf(await muscat.getByTestId("location-qty").filter({ hasText: "Main Cellar" }).getAttribute("data-qty"));
  expect(cellarAfterReceive).toBeCloseTo(cellarBefore + 1.5, 5);

  await page.getByTestId("cellar-tab-ledger").click();
  const received = page.getByTestId("movement-row").filter({ hasText: "W-MUS-01" }).filter({ hasText: reason });
  await expect(received).toBeVisible();
  await expect(received).toContainText("1.5");

  await page.goto("/records");
  await page.getByTestId("audit-action").fill("inventory.movement");
  await page.getByTestId("audit-filter").click();
  await expect(page.getByTestId("audit-row").first()).toContainText("inventory.movement");
  await expect(page.getByTestId("chain-status")).toHaveText("Verified");

  await page.goto("/inventory");
  await expect(muscat).toBeVisible();
  await page.getByTestId("transfer-sku").selectOption("W-MUS-01");
  await page.getByTestId("transfer-from").selectOption({ label: "Main Cellar" });
  await page.getByTestId("transfer-to").selectOption({ label: "Main Bar" });
  await page.getByTestId("transfer-qty").fill("1");
  const cellarAtTransfer = qtyOf(await muscat.getByTestId("location-qty").filter({ hasText: "Main Cellar" }).getAttribute("data-qty"));
  const barAtTransfer = qtyOf(await muscat.getByTestId("location-qty").filter({ hasText: "Main Bar" }).getAttribute("data-qty"));
  const beforeTransfer = qtyOf(await muscat.getByTestId("sku-on-hand").textContent());
  await page.getByTestId("transfer-submit").click();
  await expect.poll(async () => qtyOf(await muscat.getByTestId("location-qty").filter({ hasText: "Main Cellar" }).getAttribute("data-qty"))).toBeCloseTo(cellarAtTransfer - 1, 2);
  await expect.poll(async () => qtyOf(await muscat.getByTestId("location-qty").filter({ hasText: "Main Bar" }).getAttribute("data-qty"))).toBeCloseTo(barAtTransfer + 1, 2);
  await expect.poll(async () => qtyOf(await muscat.getByTestId("sku-on-hand").textContent())).toBeCloseTo(beforeTransfer, 2);
});
