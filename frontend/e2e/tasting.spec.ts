import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";

test("plan a tasting, score two samples, and download the calendar", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tastings");
  await expect(page.getByRole("heading", { name: "Tasting sessions" })).toBeVisible();
  const plan = page.getByTestId("tasting-plan");
  await expect(plan).toBeEnabled();
  await page.getByTestId("tasting-supplier").selectOption({ label: "Kermit Lynch Wine Merchant" });
  await page.getByTestId("tasting-title").fill("Phone Loire tasting");
  await page.getByTestId("tasting-when").fill("2026-12-01T15:00");
  await plan.click();
  await expect(page.getByTestId("tasting-session-title")).toHaveText("Phone Loire tasting");
  const downloadLink = page.getByTestId("tasting-ics");
  await expect(downloadLink).toBeVisible();

  await page.getByTestId("tasting-add-sample").click();
  await expect(page.getByTestId("sample-card")).toHaveCount(1);
  await page.getByTestId("tasting-add-sample").click();
  await expect(page.getByTestId("sample-card")).toHaveCount(2);

  const scores = page.getByTestId("sample-score");
  const saves = page.getByTestId("sample-score-save");
  await scores.nth(0).fill("80");
  await saves.nth(0).click();
  await expect(page.getByTestId("sample-score-value").nth(0)).toHaveText("Score 80");
  await scores.nth(1).fill("90");
  await saves.nth(1).click();
  await expect(page.getByTestId("sample-score-value").nth(1)).toHaveText("Score 90");

  const [download] = await Promise.all([page.waitForEvent("download"), downloadLink.click()]);
  const text = await fs.readFile(await download.path(), "utf8");
  expect(text).toContain("BEGIN:VCALENDAR");
  expect(text).toContain("DTSTART:20261201T150000Z");
  expect(text).toContain("END:VCALENDAR");

  for (const target of [plan, page.getByTestId("tasting-add-sample"), downloadLink, saves.nth(0)]) {
    const box = await target.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
