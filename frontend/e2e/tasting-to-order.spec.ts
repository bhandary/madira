import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("a tasting buy becomes a draft purchase order the owner can approve", async ({ page }) => {
  await page.goto("/tastings");
  await expect(page.getByRole("heading", { name: "Tasting sessions" })).toBeVisible();
  const plan = page.getByTestId("tasting-plan");
  await expect(plan).toBeEnabled();
  await page.getByTestId("tasting-supplier").selectOption({ label: "Kermit Lynch Wine Merchant" });
  await page.getByTestId("tasting-title").fill("Phone order tasting");
  await page.getByTestId("tasting-when").fill("2026-12-01T15:00");
  await plan.click();
  await expect(page.getByTestId("tasting-session-title")).toHaveText("Phone order tasting");

  await page.getByTestId("tasting-add-sample").click();
  const card = page.getByTestId("sample-card");
  await expect(card).toHaveCount(1);
  await card.getByTestId("sample-product").selectOption({ label: "Muscadet Domaine de l'Ecu" });
  await card.getByTestId("sample-quote").fill("1800");
  await card.getByTestId("sample-quote-save").click();
  await expect(card.getByTestId("sample-bottle")).toContainText("USD");
  await card.getByTestId("sample-score").fill("88");
  await card.getByTestId("sample-score-save").click();
  await expect(card.getByTestId("sample-score-value")).toHaveText("Score 88");

  const buy = card.getByTestId("sample-buy");
  for (const target of [plan, buy]) {
    const box = await target.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  }
  await buy.click();
  const orderLink = card.getByTestId("sample-po");
  await expect(orderLink).toBeVisible();
  const number = await orderLink.getAttribute("data-po");
  expect(number).toBeTruthy();

  await page.goto("/purchasing");
  await expect(page.getByRole("heading", { name: "Purchasing" })).toBeVisible();
  await page.locator(`[data-testid="po-card"][data-po="${number}"]`).click();
  const detail = page.getByTestId("po-detail");
  await expect(detail.getByTestId("po-status")).toHaveText("draft");
  const approve = page.getByTestId("po-approve");
  const approveBox = await approve.boundingBox();
  expect(approveBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await approve.click();
  await expect(detail.getByTestId("po-status")).toHaveText("approved");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
