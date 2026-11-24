import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

test("a sommelier approves a lesson and a server takes its quiz", async ({ page }) => {
  await page.goto("/training");
  await expect(page.getByTestId("training-actor")).toContainText("Demo Owner");
  await page.getByTestId("lesson-position").selectOption("server");
  await page.getByTestId("lesson-draft").click();
  const draft = page.getByTestId("draft-lesson").filter({ hasText: "Server service: Opening a still bottle" }).first();
  await expect(draft).toBeVisible({ timeout: 30_000 });
  await draft.getByTestId("lesson-approve").click();
  await page.getByTestId("tab-lessons").click();
  await expect(page.getByTestId("my-lesson").filter({ hasText: "Server service: Opening a still bottle" }).first()).toBeVisible();

  await page.getByRole("button", { name: "More" }).click();
  await page.getByTestId("mobile-menu").getByTestId("persona-ana").click();
  await expect(page.getByTestId("training-actor")).toContainText("Ana");
  const lesson = page.getByTestId("my-lesson").filter({ hasText: "Server service: Opening a still bottle" }).first();
  await expect(lesson).toBeVisible();
  await lesson.getByTestId("lesson-quiz").click();
  const questions = page.getByTestId("quiz-question");
  await expect(questions.first()).toBeVisible();
  const count = await questions.count();
  expect(count).toBeGreaterThan(0);
  const choice = questions.first().getByTestId("quiz-choice").first();
  const height = await choice.evaluate((node) => (node as HTMLElement).getBoundingClientRect().height);
  expect(height).toBeGreaterThanOrEqual(44);
  for (let index = 0; index < count; index += 1) {
    await questions.nth(index).getByTestId("quiz-choice").first().click();
  }
  await page.getByTestId("quiz-submit").click();
  await expect(page.getByTestId("quiz-score")).toBeVisible();
  await expect(page.getByTestId("quiz-next-review")).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
