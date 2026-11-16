import { expect, test } from "@playwright/test";
import fs from "node:fs";

const apiKey = "sk-test-settings-key-1234";

test.describe("settings", () => {
  test("save a provider key, leave demo mode, then restore it", async ({ page, request }) => {
    const before = await request.get("/madira-api/settings/llm");
    expect(before.ok()).toBeTruthy();

    await request.delete("/madira-api/settings/llm");

    try {
      await page.goto("/");
      await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);

      await page.getByRole("link", { name: "Settings" }).click();
      await expect(page.getByTestId("settings-page")).toBeVisible();
      await expect(page.getByTestId("settings-password")).toHaveCount(0);
      await expect(page.getByTestId("settings-key-hint")).toContainText(/No key saved/i);

      await page.getByTestId("settings-provider").selectOption("openai");
      await page.getByTestId("settings-model").fill("gpt-4.1-mini");
      await page.getByTestId("settings-api-key").fill(apiKey);
      await page.getByTestId("settings-save").click();

      await expect(page.getByTestId("settings-key-hint")).toContainText("ends in …1234");
      await expect(page.getByTestId("settings-page")).not.toContainText(apiKey);
      await expect(page.getByTestId("mode-banner")).not.toContainText(/DEMO MODE/i);
      await expect(page.getByTestId("settings-mode")).toContainText(/LIVE/i);

      fs.mkdirSync("/opt/cursor/artifacts/screenshots", { recursive: true });
      await page.screenshot({
        path: "/opt/cursor/artifacts/screenshots/settings-page.png",
        fullPage: true,
      });

      await page.getByTestId("settings-remove").click();
      await expect(page.getByTestId("settings-key-hint")).toContainText(/No key saved/i);
      await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);
    } finally {
      await request.delete("/madira-api/settings/llm");
    }
  });
});
