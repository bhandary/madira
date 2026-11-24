import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("owner approves a case-rounded PO and the PDF lands in the vault", async ({ page }) => {
  await page.goto("/purchasing");
  await expect(page.getByTestId("mode-banner")).not.toContainText(/connecting/i);
  await expect(page.getByRole("heading", { level: 1, name: "Purchasing" })).toBeVisible();

  const kermit = page.getByTestId("supplier-card").filter({ hasText: "Kermit Lynch Wine Merchant" });
  await expect(kermit.getByTestId("supplier-case-size")).toContainText("12");
  await expect(kermit.getByTestId("supplier-delivery-days")).toContainText("Tue");
  await expect(kermit.getByTestId("supplier-contact")).toContainText("Claire Vasseur");

  await page.getByTestId("draft-supplier").selectOption({ label: "Kermit Lynch Wine Merchant" });
  await expect(page.getByTestId("draft-cases")).toContainText("1 case of 12");
  await expect(page.getByTestId("draft-quantity")).toContainText("12 bottles");
  await expect(page.getByTestId("draft-minimum")).toContainText("Minimum not met");
  await expect(page.getByTestId("draft-delivery")).toContainText(/\d{4}-\d{2}-\d{2}/);

  await page.getByTestId("draft-submit").click();
  await expect(page.getByTestId("approval-card")).toBeVisible();
  const detail = page.getByTestId("po-detail");
  await expect(detail.getByTestId("po-status")).toHaveText("draft");
  await page.getByTestId("po-comment").fill("Send the Tuesday truck.");
  await page.getByTestId("po-approve").click();
  await expect(detail.getByTestId("po-status")).toHaveText("approved");
  await expect(page.getByTestId("approval-decision")).toContainText("approved");

  await page.getByTestId("po-send").click();
  await expect(detail.getByTestId("po-status")).toHaveText("sent");
  const href = await page.getByTestId("po-pdf").getAttribute("href");
  expect(href).toBeTruthy();
  const pdf = await page.request.get(href!);
  expect(pdf.ok()).toBeTruthy();
  expect(pdf.headers()["content-type"]).toContain("application/pdf");
  const body = await pdf.body();
  expect(body.subarray(0, 5).toString()).toBe("%PDF-");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  await page.goto("/records");
  await page.getByTestId("audit-action").fill("purchase_order.sent");
  await page.getByTestId("audit-filter").click();
  await expect(page.getByTestId("audit-row").first()).toContainText("purchase_order.sent");
  await expect(page.getByTestId("chain-status")).toHaveText("Verified");
  await expect(page.getByTestId("document-row").filter({ hasText: ".pdf" }).first()).toBeVisible();
});
