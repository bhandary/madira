import { expect, test, type Page } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

async function enterPin(page: Page, pin: string) {
  const dots = page.getByTestId("tablet-pin-dots");
  for (let index = 0; index < pin.length; index += 1) {
    await page.getByTestId(`tablet-digit-${pin[index]}`).click();
    await expect(dots).toHaveText("•".repeat(index + 1));
  }
}

async function submitPin(page: Page) {
  const unlock = page.waitForResponse(
    (res) => res.url().includes("/tablet/unlock") && res.request().method() === "POST",
  );
  await expect(page.getByTestId("tablet-pin-submit")).toBeEnabled();
  await page.getByTestId("tablet-pin-submit").click();
  await unlock;
}

async function savePin(page: Page, pin: string) {
  await expect(page.getByTestId("my-pin")).toBeVisible();
  await page.getByTestId("my-pin").fill(pin);
  await page.getByTestId("my-pin-save").click();
  await expect(page.getByTestId("my-pin-saved")).toBeVisible();
}

async function prepareStaffPin(page: Page) {
  await page.goto("/settings");
  await expect(page.getByTestId("tablet-enable")).toBeVisible();
  const anaRow = page.locator('[data-testid="tablet-clear-row"][data-name="Ana"]');
  if (await anaRow.count()) {
    const cleared = page.waitForResponse(
      (res) =>
        res.url().includes("/team/members/") &&
        res.url().includes("/pin") &&
        res.request().method() === "DELETE",
    );
    await anaRow.getByTestId("tablet-clear-pin").click();
    await cleared;
  }
  await savePin(page, "1357");
  await expect(page.getByTestId("tablet-enable")).toBeEnabled();

  await page.request.post("/madira-api/auth/demo-persona", { data: { slug: "ana" } });
  await page.goto("/");
  await savePin(page, "2468");

  await page.request.post("/madira-api/auth/demo-persona", { data: { slug: "owner" } });
  await page.goto("/settings");
  await expect(page.getByTestId("tablet-enable")).toBeEnabled();
  await page.getByTestId("tablet-enable").click();
  await expect(page.getByTestId("tablet-picker")).toBeVisible();
}

test("set a PIN, share the tablet, switch user, and auto-lock", async ({ page }) => {
  await prepareStaffPin(page);
  await page.locator('[data-testid="tablet-person"][data-name="Ana"]').click();
  await enterPin(page, "2468");
  await page.clock.install();
  await submitPin(page);
  await expect(page.getByTestId("tablet-actor")).toContainText("Signed in as Ana");

  await page.clock.runFor("16:00");
  await expect(page.getByTestId("tablet-picker")).toBeVisible();
  await expect(page.getByTestId("tablet-actor")).toHaveCount(0);
});

test("a wrong PIN locks the tablet", async ({ page }) => {
  await prepareStaffPin(page);
  await page.locator('[data-testid="tablet-person"][data-name="Ana"]').click();
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await enterPin(page, "0000");
    await submitPin(page);
  }
  await expect(page.getByTestId("tablet-pin-error")).toContainText("locked");
  await enterPin(page, "2468");
  await submitPin(page);
  await expect(page.getByTestId("tablet-pin-error")).toContainText("locked");
  await expect(page.getByTestId("tablet-actor")).toHaveCount(0);
});
