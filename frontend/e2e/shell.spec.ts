import { expect, test } from "@playwright/test";

const routes = [
  ["/", "Ask the Head Sommelier"],
  ["/menu", "Menu & pairings"],
  ["/list", "List curation"],
  ["/inventory", "Inventory & purchasing"],
  ["/training", "Staff training"],
  ["/suppliers", "Supplier tastings"],
  ["/settings", "Settings"],
  ["/login", "Sign in"],
] as const;

for (const viewport of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`shell fits ${viewport.name} without horizontal overflow`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    for (const [route, title] of routes) {
      await page.goto(route);
      await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);
      await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, route).toBeLessThanOrEqual(1);
    }
  });
}

test("keyboard focus is visible on the first control", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.keyboard.press("Tab");
  const focus = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el) return { outline: "none", width: "0px", tag: "" };
    const style = getComputedStyle(el);
    return { outline: style.outlineStyle, width: style.outlineWidth, tag: el.tagName };
  });
  expect(focus.outline).not.toBe("none");
  expect(parseFloat(focus.width)).toBeGreaterThan(0);
});

test("mobile sections menu reveals navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/inventory");
  await expect(page.getByRole("link", { name: "Supplier tastings" })).toBeHidden();
  await page.getByRole("button", { name: "Sections" }).click();
  await expect(page.getByRole("link", { name: "Supplier tastings" })).toBeVisible();
});
