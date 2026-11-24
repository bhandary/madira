import { expect, test } from "@playwright/test";

test("records shows a verified chain, files a document, and logs the next change", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.getByTestId("mode-banner")).not.toContainText(/connecting/i);
  await page.getByRole("navigation", { name: "Sections" }).getByRole("link", { name: "Records" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Records" })).toBeVisible();
  await expect(page.getByTestId("chain-status")).toHaveText("Verified");

  const license = page.getByTestId("document-row").filter({ hasText: "maison-madira-liquor-license.txt" });
  await expect(license).toBeVisible();
  await expect(license.getByTestId("document-sha")).toHaveAttribute("data-sha", /^[a-f0-9]{64}$/);
  await expect(license.getByTestId("document-size")).toContainText(/\d/);
  await expect(page.getByTestId("retention-years")).toHaveValue("7");

  const note = "Received 6 cases of Muscadet for the vault.";
  const filename = `cellar-delivery-${Date.now()}.txt`;
  await page.getByTestId("vault-doc-type").selectOption("delivery_note");
  await page.getByTestId("vault-file").setInputFiles({
    name: filename,
    mimeType: "text/plain",
    buffer: Buffer.from(note),
  });
  await page.getByTestId("vault-upload").click();
  const uploaded = page.getByTestId("document-row").filter({ hasText: filename });
  await expect(uploaded).toBeVisible();
  const href = await uploaded.getByTestId("document-download").getAttribute("href");
  expect(href).toBeTruthy();
  const downloaded = await page.request.get(href!);
  expect(downloaded.ok()).toBeTruthy();
  expect(await downloaded.text()).toBe(note);
  await expect(page.getByTestId("audit-table")).toContainText("document.store");

  await page.getByTestId("retention-years").fill("9");
  await page.getByTestId("retention-save").click();
  await expect(page.getByTestId("retention-years")).toHaveValue("9");
  await expect(page.getByTestId("audit-table")).toContainText("retention.update");
  await expect(page.getByTestId("chain-status")).toHaveText("Verified");

  const adjusted = await page.request.patch("/madira-api/inventory/W-MUS-01", { data: { on_hand: 4 } });
  expect(adjusted.ok()).toBeTruthy();
  await page.getByTestId("audit-action").fill("inventory.adjust");
  await page.getByTestId("audit-filter").click();
  await expect(page.getByTestId("audit-row").first()).toContainText("inventory.adjust");
  await expect(page.getByTestId("chain-status")).toHaveText("Verified");

  await page.getByTestId("audit-action").fill("");
  await page.getByTestId("audit-filter").click();
  await expect(page.getByTestId("audit-table")).toContainText("document.store");
  await page.getByTestId("retention-years").fill("7");
  await page.getByTestId("retention-save").click();
  await expect(page.getByTestId("retention-years")).toHaveValue("7");
  await expect(page.getByTestId("audit-table")).toContainText("retention.update");
  await expect(page.getByTestId("chain-status")).toHaveText("Verified");
});

test("records fits a phone and keeps 44px targets", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByTestId("mode-banner")).not.toContainText(/connecting/i);
  await page.getByRole("button", { name: "More", exact: true }).click();
  await page.getByTestId("mobile-menu").getByRole("link", { name: "Records" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Records" })).toBeVisible();
  await expect(page.getByTestId("chain-status")).toHaveText("Verified");

  for (const testId of ["vault-upload", "audit-filter", "retention-save"]) {
    const box = await page.getByTestId(testId).boundingBox();
    expect(box, testId).not.toBeNull();
    expect(box!.height, testId).toBeGreaterThanOrEqual(44);
    expect(box!.width, testId).toBeGreaterThanOrEqual(44);
  }
  const download = await page.getByTestId("document-download").first().boundingBox();
  expect(download).not.toBeNull();
  expect(download!.height).toBeGreaterThanOrEqual(44);

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});
