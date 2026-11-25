import { expect, test } from "@playwright/test";
import { curateFromMenu, waitForListDesk } from "./listDesk";

test.use({ viewport: { width: 390, height: 844 } });

test("the sommelier submits, the owner approves, and the QR page loads logged out", async ({ page, browser }) => {
  await page.request.post("/madira-api/auth/demo-persona", { data: { slug: "lea" } });
  await page.goto("/list");
  await waitForListDesk(page);
  await curateFromMenu(page);
  const editor = page.getByTestId("list-editor");
  await expect(editor).toBeVisible({ timeout: 60_000 });
  await expect(editor.getByTestId("list-item").first()).toBeVisible();

  const review = editor.getByTestId("list-diff-load");
  const reviewBox = await review.boundingBox();
  expect(reviewBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await review.click();
  await expect(editor.getByTestId("list-diff-added")).toContainText("Added");

  const submit = editor.getByTestId("list-submit");
  const submitBox = await submit.boundingBox();
  expect(submitBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await submit.click();
  await expect(editor.getByTestId("list-pending")).toBeVisible();

  const listId = await page.getByTestId("list-picker").inputValue();
  await page.request.post("/madira-api/auth/demo-persona", { data: { slug: "owner" } });
  await page.goto("/");
  await expect(page.getByTestId("tonight-approval").filter({ hasText: "List publish" }).first()).toBeVisible();

  await page.goto("/list");
  await page.getByTestId("list-picker").selectOption(listId);
  const approve = page.getByTestId("list-approve");
  await expect(approve).toBeVisible();
  const approveBox = await approve.boundingBox();
  expect(approveBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await approve.click();
  const qr = page.getByTestId("list-qr");
  await expect(qr).toBeVisible();
  await expect.poll(async () => qr.evaluate((node: HTMLImageElement) => node.naturalWidth)).toBeGreaterThan(20);
  const href = await page.getByTestId("list-public-url").getAttribute("href");
  expect(href).toMatch(/^\/l\//);

  const guest = await browser.newContext();
  const guestPage = await guest.newPage();
  await guestPage.setViewportSize({ width: 390, height: 844 });
  await guestPage.goto(href || "/");
  await expect(guestPage.getByTestId("public-list")).toBeVisible();
  await expect(guestPage.getByTestId("public-venue")).not.toHaveText("");
  await expect(guestPage.getByTestId("public-item").first()).toBeVisible();
  await expect(guestPage.getByTestId("public-price").filter({ hasText: /\d/ }).first()).toBeVisible();
  await expect(guestPage.getByTestId("phone-tabs")).toHaveCount(0);
  await expect(guestPage.getByTestId("mode-banner")).toHaveCount(0);
  await expect(guestPage.getByText(/margin/i)).toHaveCount(0);
  await expect(guestPage.getByText(/\bcost\b/i)).toHaveCount(0);
  const overflow = await guestPage.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await guest.close();
});
