import { expect, type Page, type Response } from "@playwright/test";

/**
 * The curate control is in the server HTML before its click handler exists.
 * It stays disabled until the client list load settles, which is after hydration.
 */
export async function waitForListDesk(page: Page) {
  await expect(page.getByRole("heading", { name: "List curation" })).toBeVisible();
  await expect(page.getByTestId("list-curate")).toBeEnabled();
}

export async function curateFromMenu(page: Page): Promise<Response> {
  const curated = page.waitForResponse(
    (res) => res.url().includes("/lists/curate") && res.request().method() === "POST",
  );
  await page.getByTestId("list-curate").click();
  const response = await curated;
  expect(response.ok()).toBeTruthy();
  return response;
}
