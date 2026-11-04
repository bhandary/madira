import { expect, test } from "@playwright/test";

const quotaMessage = "OpenAI rejected the API key (429). You have no credits remaining";

test("sommelier run shows the provider error", async ({ page }) => {
  await page.route("**/madira-api/agent/run", (route) =>
    route.fulfill({
      status: 429,
      contentType: "application/json",
      body: JSON.stringify({ detail: "You have no credits remaining" }),
    }),
  );
  await page.goto("/menu");
  await page.getByTestId("menu-workbench-submit").click();
  const error = page.getByTestId("agent-error");
  await expect(error).toContainText("You have no credits remaining");
  await expect(error).not.toContainText("sk-");
});

test("an empty provider failure is still visible", async ({ page }) => {
  await page.route("**/madira-api/agent/run", (route) =>
    route.fulfill({ status: 500, contentType: "text/plain", body: "" }),
  );
  await page.goto("/menu");
  await page.getByTestId("menu-workbench-submit").click();
  await expect(page.getByTestId("agent-error")).toContainText("Request failed (500)");
});

test("settings save shows a quota rejection", async ({ page }) => {
  const secret = "sk-quota-should-not-appear";
  await page.route("**/madira-api/settings/**", async (route) => {
    const request = route.request();
    const url = request.url();
    if (request.method() === "POST" && url.endsWith("/settings/session")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ token: "session-token", expires_in: 28800 }),
      });
      return;
    }
    if (request.method() === "GET" && url.endsWith("/settings/llm")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          configured: false,
          stored: false,
          provider: "openai",
          model: "gpt-4.1-mini",
          key_hint: null,
          demo_mode: true,
          demo_forced: false,
          source: "demo",
          label: "DEMO MODE — deterministic fixtures, no API key",
          warning: "",
          default_models: {
            openai: "gpt-4.1-mini",
            anthropic: "claude-haiku-4-5-20251001",
            google_genai: "gemini-3.5-flash",
          },
        }),
      });
      return;
    }
    if (request.method() === "POST" && url.endsWith("/settings/llm")) {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: quotaMessage }),
      });
      return;
    }
    await route.continue();
  });

  await page.goto("/settings");
  await page.getByTestId("settings-password").fill("anything");
  await page.getByTestId("settings-unlock").click();
  await page.getByTestId("settings-api-key").fill(secret);
  await page.getByTestId("settings-save").click();
  const error = page.getByTestId("settings-error");
  await expect(error).toContainText("You have no credits remaining");
  await expect(error).toContainText("429");
  await expect(page.getByTestId("settings-page")).not.toContainText(secret);
});
