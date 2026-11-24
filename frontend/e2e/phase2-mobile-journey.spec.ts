import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("phone count, order, receive, storage excursion, and audit pack export", async ({ page }) => {
  await page.goto("/inventory/count");
  await expect(page.getByTestId("mode-banner")).not.toContainText(/connecting/i);
  await page.getByTestId("count-location").selectOption({ label: "Main Cellar" });
  await page.getByTestId("count-start").click();
  await expect(page.getByTestId("count-sheet")).toBeVisible();
  await page.getByTestId("count-sku").selectOption("S-TOK-01");
  await page.getByTestId("count-plus-one").click();
  await expect(page.getByTestId("count-qty")).toHaveValue("1");
  await page.getByTestId("count-save").click();
  await expect(page.getByTestId("count-line").filter({ hasText: "S-TOK-01" })).toBeVisible();
  await page.getByTestId("count-submit").click();
  await expect(page.getByTestId("variance-report")).toBeVisible();
  await page.getByTestId("count-approve").click();
  await expect(page.getByTestId("count-approved")).toBeVisible();

  await page.goto("/inventory");
  const stock = page.locator("[data-testid=sku-row][data-sku='W-MUS-01']");
  await expect(stock).toBeVisible();
  const before = Number(await stock.getByTestId("sku-on-hand").innerText());

  await page.goto("/purchasing");
  await expect(page.getByRole("heading", { level: 1, name: "Purchasing" })).toBeVisible();
  await page.getByTestId("draft-supplier").selectOption({ label: "Kermit Lynch Wine Merchant" });
  await page.getByTestId("draft-bottles").fill("12");
  await page.getByTestId("draft-cost").fill("1800");
  await page.getByTestId("draft-submit").click();
  const detail = page.getByTestId("po-detail");
  await expect(detail.getByTestId("po-status")).toHaveText("draft");
  await page.getByTestId("po-approve").click();
  await expect(detail.getByTestId("po-status")).toHaveText("approved");
  await page.getByTestId("po-send").click();
  await expect(detail.getByTestId("po-status")).toHaveText("sent");
  const pdfHref = await page.getByTestId("po-pdf").getAttribute("href");
  expect(pdfHref).toBeTruthy();
  const sentPdf = await page.request.get(pdfHref!);
  expect(sentPdf.ok()).toBeTruthy();
  expect((await sentPdf.body()).subarray(0, 5).toString()).toBe("%PDF-");

  const invoiceName = `phase2-invoice-${Date.now()}.pdf`;
  await page.getByTestId("invoice-number").fill(`P2-${Date.now()}`);
  await page.getByTestId("invoice-unit-cost").fill("1800");
  await page.getByTestId("invoice-file").setInputFiles({
    name: invoiceName,
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\nphase2 invoice\n%%EOF\n"),
  });
  await page.getByTestId("invoice-upload").click();
  await expect(page.getByTestId("invoice-lines")).toContainText("W-MUS-01");
  const line = page.getByTestId("receiving-line").filter({ hasText: "W-MUS-01" });
  await line.getByTestId("counted-qty").fill("12");
  await page.getByTestId("stage-receipt").click();
  if ((await page.getByTestId("receipt-flag").count()) > 0) {
    await page.getByTestId("acknowledge-discrepancies").check();
  }
  await page.getByTestId("accept-delivery").click();
  await expect(detail.getByTestId("po-status")).toHaveText("received");

  await page.goto("/inventory");
  await expect(stock.getByTestId("sku-on-hand")).toHaveText(String(before + 12));
  const cellar = page.getByTestId("zone-card").filter({ hasText: "Main Cellar" });
  await expect(cellar).toBeVisible();
  await expect(cellar.getByTestId("zone-status")).toHaveText("OK");
  await cellar.getByTestId("zone-temp").fill("22");
  await cellar.getByTestId("zone-humidity").fill("80");
  await cellar.getByTestId("zone-record").click();
  await expect(cellar.getByTestId("zone-status")).toHaveText("Excursion");
  await expect(cellar.getByTestId("affected-sku").first()).toBeVisible();
  const inventoryOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(inventoryOverflow).toBeLessThanOrEqual(1);

  await page.goto("/records");
  await expect(page.getByTestId("document-row").filter({ hasText: ".pdf" }).first()).toBeVisible();
  await expect(page.getByTestId("document-row").filter({ hasText: invoiceName })).toBeVisible();
  await expect(page.getByTestId("chain-status")).toHaveText("Verified");
  await expect(page.getByTestId("audit-pack-valuation")).toBeVisible();
  await expect(page.getByTestId("audit-pack-purchases")).toBeVisible();
  await expect(page.getByTestId("audit-pack-invoices")).toBeVisible();
  await expect(page.getByTestId("audit-pack-variance")).toBeVisible();
  await expect(page.getByTestId("audit-pack-waste")).toBeVisible();
  await expect(page.getByTestId("audit-pack-retention")).toContainText("7");
  await expect(page.getByTestId("audit-pack-chain")).toContainText("Verified");

  for (const testId of ["download-audit-pack", "download-journal-csv", "download-summary-pdf"]) {
    const href = await page.getByTestId(testId).getAttribute("href");
    expect(href).toBeTruthy();
    const response = await page.request.get(href!);
    expect(response.status()).toBe(200);
    const body = await response.body();
    expect(body.byteLength).toBeGreaterThan(32);
    if (testId === "download-audit-pack") expect(body.subarray(0, 2).toString()).toBe("PK");
    if (testId === "download-journal-csv") {
      const text = body.toString();
      expect(text).toContain("Date,Reference,Description,Account,Debit,Credit,Supplier,Currency,DocumentHash");
      expect(text).toContain("Inventory Asset");
    }
    if (testId === "download-summary-pdf") expect(body.subarray(0, 5).toString()).toBe("%PDF-");
  }

  const recordsOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(recordsOverflow).toBeLessThanOrEqual(1);
});
