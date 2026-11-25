import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

function iso(offset: number) {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  const year = day.getFullYear();
  const month = String(day.getMonth() + 1).padStart(2, "0");
  const date = String(day.getDate()).padStart(2, "0");
  return `${year}-${month}-${date}`;
}

test("the owner invites, Ana roleplays the skeptic, and Mia sees progress and an expiring certificate", async ({ page }) => {
  const email = `new.server.${Date.now()}@example.com`;
  await page.goto("/training");
  await expect(page.getByTestId("training-actor")).toContainText("Demo Owner");
  await page.getByTestId("tab-team").click();
  await page.getByTestId("invite-email").fill(email);
  await page.getByTestId("invite-role").selectOption("Staff");
  await page.getByTestId("invite-position").selectOption("server");
  const invite = page.getByTestId("invite-submit");
  const inviteBox = await invite.boundingBox();
  expect(inviteBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await invite.click();
  await expect(page.getByTestId("invite-row").filter({ hasText: email })).toBeVisible();

  await page.getByTestId("certificate-user").selectOption({ label: "Mia" });
  await page.getByTestId("certificate-kind").selectOption("responsible_service");
  await page.getByTestId("certificate-label").fill("Responsible service");
  await page.getByTestId("certificate-issued").fill(iso(-20));
  await page.getByTestId("certificate-expires").fill(iso(10));
  await page.getByTestId("certificate-file").setInputFiles({
    name: "certificate.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("responsible service card"),
  });
  await page.getByTestId("certificate-save").click();
  await expect(page.getByTestId("certificate-expiring").filter({ hasText: /^Mia\b/ }).first()).toBeVisible();

  await page.request.post("/madira-api/auth/demo-persona", { data: { slug: "ana" } });
  await page.goto("/training");
  await expect(page.getByTestId("training-actor")).toContainText("Ana");
  await expect(page.getByTestId("tab-team")).toHaveCount(0);
  await page.getByTestId("tab-practice").click();
  await page.getByTestId("roleplay-persona-skeptic").click();
  const start = page.getByTestId("roleplay-start");
  const startBox = await start.boundingBox();
  expect(startBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await start.click();
  await expect(page.getByTestId("roleplay-guest").first()).toBeVisible();
  await page.getByTestId("roleplay-reply").fill("I hear you. The bright glass has more acidity, and the price is easier by the glass.");
  await page.getByTestId("roleplay-send").click();
  await expect(page.getByTestId("roleplay-guest").last()).toBeVisible();
  await page.getByTestId("roleplay-finish").click();
  await expect(page.getByTestId("roleplay-rubric")).toBeVisible();
  await expect(page.getByTestId("roleplay-score")).toBeVisible();
  await expect(page.getByTestId("roleplay-criterion")).toHaveCount(4);

  await page.request.post("/madira-api/auth/demo-persona", { data: { slug: "mia" } });
  await page.goto("/training");
  await expect(page.getByTestId("training-actor")).toContainText("Mia");
  await page.getByTestId("tab-team").click();
  await expect(page.getByTestId("progress-person").filter({ has: page.getByText("Ana", { exact: true }) })).toBeVisible();
  await expect(page.getByTestId("certificate-expiring").filter({ hasText: /^Mia\b/ }).first()).toBeVisible();
  await page.goto("/");
  await expect(page.getByTestId("tonight-certificate").filter({ hasText: /^Mia\b/ }).first()).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
