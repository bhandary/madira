import { expect, test } from "@playwright/test";

test("demo chat gets an assistant reply", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("mode-banner")).toContainText(/DEMO MODE/i);
  const chat = page.getByTestId("copilot-chat").first();
  await chat.getByPlaceholder("Type a message...").fill("Show the supplier tasting calendar.");
  await chat.getByRole("button", { name: "Send message" }).click();
  await expect(chat).toContainText(/Head Sommelier/i, { timeout: 90_000 });
  await expect(chat.getByTestId("copilot-chat-error")).toHaveCount(0);
  await expect(page.getByText("A2UI render error")).toHaveCount(0);
  await expect(chat.getByTestId("tasting-calendar")).toBeVisible();
});
