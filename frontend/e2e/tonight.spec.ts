import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("Ana reads tonight, acknowledges it, and looks up a bottle", async ({ page }) => {
  await page.goto("/");
  const rebuilt = await page.request.post("/madira-api/tonight/briefing/rebuild");
  expect(rebuilt.ok()).toBeTruthy();
  const published = await page.request.post("/madira-api/tonight/briefing/publish");
  expect(published.ok()).toBeTruthy();
  await page.request.post("/madira-api/auth/demo-persona", { data: { slug: "ana" } });
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1, name: "Tonight" })).toBeVisible();
  const tabs = page.getByTestId("phone-tabs");
  await expect(tabs.getByRole("link")).toHaveCount(3);
  await expect(tabs.getByRole("link", { name: "Tonight" })).toBeVisible();
  await expect(tabs.getByRole("link", { name: "Lookup" })).toBeVisible();
  await expect(tabs.getByRole("link", { name: "Lessons" })).toBeVisible();
  await expect(tabs.getByRole("link", { name: "Menu" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "More", exact: true })).toHaveCount(0);

  const next = page.getByTestId("briefing-next");
  await expect(next).toBeVisible();
  const nextBox = await next.boundingBox();
  expect(nextBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  for (let step = 0; step < 12; step += 1) {
    if (await page.getByTestId("briefing-ack").isVisible()) break;
    await next.click();
  }
  const ack = page.getByTestId("briefing-ack");
  await expect(ack).toBeVisible();
  const ackBox = await ack.boundingBox();
  expect(ackBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await ack.click();
  await expect(page.getByTestId("briefing-acked")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  await page.goto("/lookup");
  await expect(page.getByRole("heading", { level: 1, name: "Floor lookup" })).toBeVisible();
  await page.getByTestId("lookup-query").fill("Chablis");
  await page.getByTestId("lookup-submit").click();
  const result = page.getByTestId("lookup-result").filter({ hasText: "Chablis" }).first();
  await expect(result.getByTestId("lookup-glassware")).toContainText("White wine glass");
  await expect(result.getByTestId("lookup-temperature")).toContainText("10");
  await expect(result.getByTestId("lookup-pour")).toContainText("150");
  await expect(result.getByTestId("lookup-stock")).not.toHaveText("");

  await page.goto("/menu");
  await expect(page.getByRole("heading", { level: 1, name: "Tonight" })).toBeVisible();
});
