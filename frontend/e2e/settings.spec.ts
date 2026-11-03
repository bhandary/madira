import { expect, test } from "@playwright/test";
import fs from "node:fs";

const password = process.env.MADIRA_ADMIN_PASSWORD || "";
const apiKey = "sk-test-settings-key-1234";

test.describe("settings", () => {
  test("save a provider key, leave demo mode, then restore it", async ({ page, request }) => {
    expect(password, "Set MADIRA_ADMIN_PASSWORD to the same value as the backend").not.toBe("");

    const denied = await request.get("/madira-api/settings/llm");
    expect(denied.status()).toBe(401);

    const session = await request.post("/madira-api/settings/session", { data: { password } });
    expect(session.ok()).toBeTruthy();
    const token = (await session.json()).token as string;
    const headers = { "X-Madira-Admin-Token": token };
    await request.delete("/madira-api/settings/llm", { headers });

    try {
      await page.goto("/");
      await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);

      await page.getByRole("link", { name: "Settings" }).click();
      await expect(page.getByTestId("settings-page")).toBeVisible();
      await page.getByTestId("settings-password").fill("not-the-password");
      await page.getByTestId("settings-unlock").click();
      await expect(page.getByTestId("settings-error")).toContainText(/incorrect/i);

      await page.getByTestId("settings-password").fill(password);
      await page.getByTestId("settings-unlock").click();
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
      await request.delete("/madira-api/settings/llm", { headers });
    }
  });
});
