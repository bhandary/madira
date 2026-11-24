import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("phone count queues offline, posts the variance, and accepts a par proposal", async ({ page, context }) => {
  await page.goto("/inventory/count");
  await expect(page.getByTestId("count-location")).toBeVisible();
  await page.getByTestId("count-location").selectOption({ label: "Main Cellar" });
  await page.getByTestId("count-start").click();
  await expect(page.getByTestId("count-sheet")).toBeVisible();
  await expect(page.getByTestId("count-sku").locator("option", { hasText: "S-TOK-01" })).toHaveCount(1);

  await context.setOffline(true);
  await page.getByTestId("count-sku").selectOption("S-TOK-01");
  await page.getByTestId("count-plus-tenth").click();
  await page.getByTestId("count-minus-tenth").click();
  await page.getByTestId("count-plus-tenth").click();
  await expect(page.getByTestId("count-qty")).toHaveValue("0.1");
  await page.getByTestId("count-save").click();
  await expect(page.getByTestId("queued-offline")).toHaveText("Queued offline (1)");

  await page.getByTestId("count-sku").selectOption("W-MUS-01");
  await page.getByTestId("count-plus-one").click();
  await expect(page.getByTestId("count-qty")).toHaveValue("1");
  await page.getByTestId("count-save").click();
  await expect(page.getByTestId("queued-offline")).toHaveText("Queued offline (2)");

  await context.setOffline(false);
  await page.getByTestId("count-sync").click();
  await expect(page.getByTestId("queued-offline")).toHaveCount(0);
  await expect(page.getByTestId("count-line").filter({ hasText: "S-TOK-01" })).toBeVisible();
  await expect(page.getByTestId("count-line").filter({ hasText: "W-MUS-01" })).toBeVisible();

  await page.getByTestId("count-submit").click();
  await expect(page.getByTestId("variance-report")).toBeVisible();
  await expect(page.getByTestId("variance-line").filter({ hasText: "S-TOK-01" })).toContainText("0.1");
  await page.getByTestId("count-approve").click();
  await expect(page.getByTestId("count-approved")).toBeVisible();

  await page.goto("/inventory");
  await page.getByTestId("cellar-tab-ledger").click();
  await expect(page.locator('[data-testid="movement-row"][data-type="count_adjustment"]').first()).toBeVisible();

  await page.goto("/records");
  await page.getByTestId("audit-action").fill("count_session.approved");
  await page.getByTestId("audit-filter").click();
  await expect(page.getByTestId("audit-row").first()).toContainText("count_session.approved");
  await expect(page.getByTestId("chain-status")).toHaveText("Verified");

  await page.goto("/inventory/count");
  await page.getByTestId("par-generate").click();
  const proposal = page.getByTestId("par-proposal").first();
  await expect(proposal).toBeVisible();
  const sku = await proposal.getAttribute("data-sku");
  const proposed = await proposal.getAttribute("data-proposed");
  expect(sku).toBeTruthy();
  expect(proposed).toBeTruthy();
  await proposal.getByTestId("par-accept").click();
  await expect(page.locator(`[data-testid="par-proposal"][data-sku="${sku}"]`)).toHaveCount(0);

  await page.goto("/inventory");
  const row = page.locator(`[data-testid="sku-row"][data-sku="${sku}"]`);
  await expect(row.getByTestId("sku-par")).toHaveText(proposed!);
});
