import { expect, test, type Page } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

function shiftDate(iso: string, days: number) {
  const [year, month, day] = iso.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1, day + days));
  return next.toISOString().slice(0, 10);
}

async function acknowledgeDay(page: Page, day: string) {
  await page.goto(`/?day=${day}`);
  await expect(page.getByTestId("briefing-card")).toBeVisible();
  for (let step = 0; step < 12; step += 1) {
    if (await page.getByTestId("briefing-ack").isVisible()) break;
    if (await page.getByTestId("briefing-acked").isVisible()) return;
    await page.getByTestId("briefing-next").click();
  }
  const ack = page.getByTestId("briefing-ack");
  await expect(ack).toBeVisible();
  const box = await ack.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  await ack.click();
  await expect(page.getByTestId("briefing-acked")).toBeVisible();
}

test("curate a list, Ana finishes a week of briefings and a quiz, and the report shows 7/7", async ({ page }) => {
  await page.goto("/list");
  await expect(page.getByRole("heading", { name: "List curation" })).toBeVisible();
  await page.getByTestId("list-budget").fill("9000");
  await page.getByTestId("list-margin").fill("3.2");
  await page.getByTestId("list-target-cost").fill("31.3");
  const curate = page.getByTestId("list-curate");
  const curateBox = await curate.boundingBox();
  expect(curateBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await curate.click();
  const editor = page.getByTestId("list-editor");
  await expect(editor).toBeVisible({ timeout: 60_000 });
  const before = await editor.getByTestId("list-item").count();
  expect(before).toBeGreaterThan(0);
  await editor.getByTestId("list-item-reprice").first().click();
  await expect(editor.getByTestId("list-item")).toHaveCount(before);
  await editor.getByTestId("list-item-remove").first().click();
  await expect(editor.getByTestId("list-item")).toHaveCount(before - 1);

  const todayResponse = await page.request.post("/madira-api/tonight/briefing/rebuild");
  expect(todayResponse.ok()).toBeTruthy();
  const today = (await todayResponse.json()).service_date as string;
  const days = Array.from({ length: 7 }, (_, index) => shiftDate(today, index - 6));
  for (const day of days) {
    if (day !== today) {
      const rebuilt = await page.request.post(`/madira-api/tonight/briefing/rebuild?service_date=${day}`);
      expect(rebuilt.ok()).toBeTruthy();
    }
    const published = await page.request.post(`/madira-api/tonight/briefing/publish?service_date=${day}`);
    expect(published.ok()).toBeTruthy();
  }

  await page.request.post("/madira-api/auth/demo-persona", { data: { slug: "ana" } });
  for (const day of days) {
    await acknowledgeDay(page, day);
  }

  await page.goto("/training");
  await expect(page.getByTestId("training-actor")).toContainText("Ana");
  const lesson = page.getByTestId("my-lesson").filter({ hasText: "Tonight's pairing briefing" }).first();
  await expect(lesson).toBeVisible();
  await lesson.getByTestId("lesson-quiz").click();
  const questions = page.getByTestId("quiz-question");
  await expect(questions.first()).toBeVisible();
  const count = await questions.count();
  expect(count).toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    await questions.nth(index).getByTestId("quiz-choice").first().click();
  }
  await page.getByTestId("quiz-submit").click();
  await expect(page.getByTestId("quiz-score")).toBeVisible();

  await page.request.post("/madira-api/auth/demo-persona", { data: { slug: "owner" } });
  await page.goto("/records");
  await expect(page.getByRole("heading", { level: 1, name: "Records" })).toBeVisible();
  await page.getByTestId("briefing-report-start").fill(days[0]);
  await page.getByTestId("briefing-report-end").fill(days[6]);
  await page.getByTestId("briefing-report-load").click();
  const ana = page.getByTestId("briefing-report-person").filter({ has: page.getByText("Ana", { exact: true }) });
  await expect(ana).toHaveCount(1);
  await expect(ana).toContainText("7/7");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
