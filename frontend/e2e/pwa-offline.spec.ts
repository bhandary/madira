import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  await page
    .evaluate(async () => {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map((registration) => registration.unregister()));
      const keys = await caches.keys();
      await Promise.all(keys.map((key) => caches.delete(key)));
    })
    .catch(() => undefined);
});

test("briefing and lookup render offline, and a count syncs on reconnect", async ({ page, context }) => {
  await context.addCookies([{ name: "madira_sw", value: "1", url: "http://127.0.0.1:3000" }]);
  await page.goto("/");
  await page.waitForFunction(() => Boolean(navigator.serviceWorker?.controller));
  const rebuilt = await page.request.post("/madira-api/tonight/briefing/rebuild");
  expect(rebuilt.ok()).toBeTruthy();
  const published = await page.request.post("/madira-api/tonight/briefing/publish");
  expect(published.ok()).toBeTruthy();
  await page.reload();
  await expect(page.getByTestId("briefing-stack")).toBeVisible();
  await context.setOffline(true);
  await expect(page.getByTestId("offline-banner")).toBeVisible();
  await expect(page.getByTestId("briefing-stack")).toBeVisible();
  await context.setOffline(false);
  await expect(page.getByTestId("offline-banner")).toHaveCount(0);

  await page.goto("/lookup");
  await page.waitForResponse((response) => response.url().includes("/madira-api/lookup/pack") && response.ok());
  await context.setOffline(true);
  await expect(page.getByTestId("offline-banner")).toBeVisible();
  await page.getByTestId("lookup-query").fill("Chablis");
  await page.getByTestId("lookup-submit").click();
  const offlineResult = page.getByTestId("lookup-result").filter({ hasText: "Chablis" }).first();
  await expect(offlineResult).toBeVisible();
  await expect(offlineResult.getByTestId("lookup-glassware")).toContainText("White wine glass");
  await expect(page.getByTestId("lookup-offline")).toBeVisible();
  await context.setOffline(false);

  await page.goto("/inventory/count");
  await page.getByTestId("count-location").selectOption({ label: "Main Cellar" });
  await page.getByTestId("count-start").click();
  await expect(page.getByTestId("count-sheet")).toBeVisible();
  await context.setOffline(true);
  await expect(page.getByTestId("offline-banner")).toBeVisible();
  await expect(page.getByTestId("count-sheet")).toBeVisible();
  await page.getByTestId("count-sku").selectOption("S-TOK-01");
  await page.getByTestId("count-plus-one").click();
  await page.getByTestId("count-save").click();
  await expect(page.getByTestId("queued-offline")).toHaveText("Queued offline (1)");

  await context.setOffline(false);
  await page.getByTestId("count-sync").click();
  await expect(page.getByTestId("queued-offline")).toHaveCount(0);
  await expect(page.getByTestId("count-line").filter({ hasText: "S-TOK-01" })).toBeVisible();
});
