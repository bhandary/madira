import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const apiKey = "sk-test-settings-key-1234";
const repoRoot = path.resolve(__dirname, "../..");

function removeSavedKey() {
  const python = path.join(repoRoot, "backend/.venv/bin/python");
  execFileSync(
    python,
    [
      "-c",
      "from sqlalchemy import delete\n"
        + "from madira.db import SessionLocal\n"
        + "from madira.models import LlmCredential\n"
        + "session = SessionLocal()\n"
        + "session.execute(delete(LlmCredential))\n"
        + "session.commit()\n"
        + "session.close()\n",
    ],
    {
      cwd: repoRoot,
      env: {
        ...Object.fromEntries(
          Object.entries({ ...process.env, PYTHONPATH: "backend" }).filter(([name]) => name !== "DATABASE_URL"),
        ),
        NODE_ENV: process.env.NODE_ENV,
      },
    },
  );
}

test.describe("settings", () => {
  test("save a provider key, leave demo mode, then a session is required", async ({ page, request }) => {
    const before = await request.get("/madira-api/settings/llm");
    expect(before.ok()).toBeTruthy();

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

      const follow = await request.get("/madira-api/settings/llm");
      expect(follow.status()).toBe(401);
      const menus = await request.get("/madira-api/menus");
      expect(menus.status()).toBe(401);

      await page.reload();
      await expect(page.getByTestId("settings-signed-out")).toBeVisible();
    } finally {
      removeSavedKey();
      // The SQL delete does not rebuild the in-process graph. Ask the server
      // to drop the key again so the sommelier returns to the demo model.
      await request.delete("/madira-api/settings/llm");
    }

    await page.goto("/");
    await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);
  });
});
