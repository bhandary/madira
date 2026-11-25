import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("a tasting invite is approved, then downloaded and copied, and nothing is sent", async ({ page }) => {
  const title = `Invite ${Date.now().toString(36)}`;
  await page.goto("/tastings");
  await expect(page.getByRole("heading", { name: "Tasting sessions" })).toBeVisible();
  const brief = await page.request.post("/madira-api/sourcing/briefs");
  expect(brief.ok()).toBeTruthy();

  const plan = page.getByTestId("tasting-plan");
  await expect(plan).toBeEnabled();
  await page.getByTestId("tasting-supplier").selectOption({ label: "Kermit Lynch Wine Merchant" });
  await page.getByTestId("tasting-title").fill(title);
  await page.getByTestId("tasting-when").fill("2026-12-01T15:00");
  await plan.click();
  await expect(page.getByTestId("tasting-session-title")).toHaveText(title);

  await page.getByTestId("tasting-add-sample").click();
  const card = page.getByTestId("sample-card");
  await Promise.all([
    page.waitForResponse((res) => res.url().includes("/samples/") && res.request().method() === "PATCH" && res.ok()),
    card.getByTestId("sample-product").selectOption({ label: "Muscadet Domaine de l'Ecu" }),
  ]);

  const propose = page.getByTestId("invite-propose");
  await expect(propose).toBeEnabled();
  await expect(page.getByTestId("invite-slot").first()).toBeVisible();
  const owner = page.getByTestId("invite-staff").first();
  await owner.check();
  const proposeBox = await propose.boundingBox();
  expect(proposeBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await propose.click();

  const agenda = page.getByTestId("invite-agenda");
  await expect(agenda).toBeVisible();
  await expect(agenda).not.toHaveText(/\d/);
  const gap = page.getByTestId("invite-gap").first();
  await expect(gap).toBeVisible();
  await expect(gap).toHaveText(/\d/);
  await expect(page.getByTestId("invite-sample")).toContainText("Muscadet Domaine de l'Ecu");
  await expect(page.getByTestId("invite-status")).toHaveText("proposed");
  await expect(page.getByTestId("invite-ics")).toHaveCount(0);

  await page.goto("/");
  await expect(page.getByTestId("tonight-approval").filter({ hasText: "Tasting invite awaiting approval" }).first()).toBeVisible();

  await page.goto("/tastings");
  await expect(plan).toBeEnabled();
  await page.getByRole("button", { name: title }).click();
  const choice = page.getByTestId("invite-slot-choice").nth(1);
  await expect(choice).toBeEnabled();
  const chosen = await choice.getAttribute("data-slot");
  expect(chosen).toBeTruthy();
  await choice.check();
  const approve = page.getByTestId("invite-approve");
  const approveBox = await approve.boundingBox();
  expect(approveBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await approve.click();

  const download = page.getByTestId("invite-ics");
  await expect(download).toBeVisible();
  const href = await download.getAttribute("href");
  const ics = await page.evaluate(async (path) => {
    const res = await fetch(path || "");
    return res.text();
  }, href);
  const calendar = ics.replace(/\r\n /g, "").replace(/\n /g, "");
  expect(calendar).toContain("METHOD:REQUEST");
  expect(calendar).toContain("ATTENDEE");
  expect(calendar).toContain("claire.vasseur@kermitlynch.example");
  const compact = (chosen || "").replace(/[-:]/g, "") + "00Z";
  expect(calendar).toContain(`DTSTART:${compact}`);
  expect(calendar).not.toContain("DTSTART:20261201T150000Z");
  await expect(page.getByTestId("invite-body")).toContainText("Madira did not send it");
  await expect(page.getByTestId("invite-mailto")).toHaveAttribute("href", /^mailto:/);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByTestId("invite-copy").click();
  await expect(page.getByTestId("invite-copy")).toHaveText("Copied");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
