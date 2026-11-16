import { expect, test } from "@playwright/test";

const pages = [
  { path: "/menu", submit: "menu-workbench-submit", surface: "pairing-grid" },
  { path: "/list", submit: "list-workbench-submit", surface: "beverage-list-table" },
  { path: "/inventory", submit: "inventory-workbench-submit", surface: "purchase-order-table" },
  { path: "/training", submit: "training-workbench-submit", surface: "quiz-card" },
  { path: "/suppliers", submit: "suppliers-workbench-submit", surface: "tasting-calendar" },
];

test("each workbench page streams its agent surface", async ({ page }) => {
  test.setTimeout(600_000);
  for (const item of pages) {
    await page.goto(item.path);
    await expect(page.getByTestId("mode-banner")).not.toContainText("connecting");
    const submit = page.getByTestId(item.submit);
    await expect(submit).toBeEnabled();
    const streamed = page.waitForRequest(
      (req) => req.method() === "POST" && /\/api\/copilotkit\/agent\/[^/]+\/run$/.test(new URL(req.url()).pathname),
    );
    await submit.click();
    await streamed;
    await expect(page.getByTestId("agent-working")).toBeVisible();
    await expect(page.getByTestId(item.surface).first()).toBeVisible({ timeout: 90_000 });
  }

  await page.reload();
  await expect(page.getByTestId("mode-banner")).not.toContainText("connecting");
  await expect(page.getByTestId("agent-reply")).toContainText(/Head Sommelier/i, { timeout: 30_000 });
});
