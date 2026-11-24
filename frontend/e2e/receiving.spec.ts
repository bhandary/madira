import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("phone receiving uploads an invoice, flags the count, and posts stock", async ({ page }) => {
  await page.goto("/inventory");
  await expect(page.getByTestId("mode-banner")).not.toContainText(/connecting/i);
  const stock = page.locator("[data-testid=sku-row][data-sku='W-MUS-01']");
  await expect(stock).toBeVisible();
  const before = Number(await stock.getByTestId("sku-on-hand").innerText());

  await page.goto("/purchasing");
  await expect(page.getByRole("heading", { level: 1, name: "Purchasing" })).toBeVisible();
  await page.getByTestId("draft-supplier").selectOption({ label: "Kermit Lynch Wine Merchant" });
  await page.getByTestId("draft-bottles").fill("12");
  await page.getByTestId("draft-submit").click();
  const detail = page.getByTestId("po-detail");
  await expect(detail.getByTestId("po-status")).toHaveText("draft");
  await page.getByTestId("po-approve").click();
  await expect(detail.getByTestId("po-status")).toHaveText("approved");
  await page.getByTestId("po-send").click();
  await expect(detail.getByTestId("po-status")).toHaveText("sent");

  await expect(page.getByTestId("receive-delivery")).toBeVisible();
  await page.getByTestId("invoice-number").fill("INV-1044");
  await page.getByTestId("invoice-date").fill("2026-11-24");
  await page.getByTestId("invoice-unit-cost").fill("2000");
  await page.getByTestId("invoice-file").setInputFiles({
    name: "delivery-invoice.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"),
  });
  await page.getByTestId("invoice-upload").click();
  await expect(page.getByTestId("invoice-lines")).toContainText("W-MUS-01");
  await expect(page.getByTestId("invoice-document")).toBeVisible();

  const line = page.getByTestId("receiving-line").filter({ hasText: "W-MUS-01" });
  await line.getByTestId("counted-qty").fill("6");
  await page.getByTestId("stage-receipt").click();
  await expect(line.getByTestId("receipt-flag").filter({ hasText: "Short" })).toBeVisible();
  await expect(line.getByTestId("receipt-flag").filter({ hasText: "Price Change" })).toBeVisible();
  await page.getByTestId("acknowledge-discrepancies").check();
  await page.getByTestId("accept-delivery").click();
  await expect(detail.getByTestId("po-status")).toHaveText("part_received");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  await page.goto("/inventory");
  await expect(stock).toBeVisible();
  await expect(stock.getByTestId("sku-on-hand")).toHaveText(String(before + 6));

  await page.goto("/records");
  await expect(page.getByTestId("document-row").filter({ hasText: "delivery-invoice.pdf" })).toContainText("invoice");
  await page.getByTestId("audit-action").fill("invoice.uploaded");
  await page.getByTestId("audit-filter").click();
  await expect(page.getByTestId("audit-row").first()).toContainText("invoice.uploaded");
  await page.getByTestId("audit-action").fill("receipt.accepted");
  await page.getByTestId("audit-filter").click();
  await expect(page.getByTestId("audit-row").first()).toContainText("receipt.accepted");
  await page.getByTestId("audit-action").fill("sku.cost_changed");
  await page.getByTestId("audit-filter").click();
  await expect(page.getByTestId("audit-row").first()).toContainText("sku.cost_changed");
  await expect(page.getByTestId("chain-status")).toHaveText("Verified");
});
