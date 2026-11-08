import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const OUT = "/opt/cursor/artifacts/screenshots";
const AVATAR = "https://lh3.googleusercontent.com/a/ada";
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAL0lEQVR4nO3OIQEAAAgDMGKRgHZkhhg3E/Or7bmkEhAQEBAQEBAQEBAQEBAQSAceoo0oeQfGHvMAAAAASUVORK5CYII=",
  "base64",
);

async function unmockAuth(page: import("@playwright/test").Page) {
  for (const pattern of [
    "**/madira-api/auth/config",
    "**/madira-api/auth/me",
    "**/madira-api/auth/logout",
    "https://lh3.googleusercontent.com/**",
  ]) {
    await page.unroute(pattern).catch(() => undefined);
  }
}

async function mockAuth(
  page: import("@playwright/test").Page,
  options: { configured: boolean; user: { name: string; email: string; picture: string } | null },
) {
  let user = options.user;
  await page.route("**/madira-api/auth/config", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ configured: options.configured }),
    }),
  );
  await page.route("**/madira-api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ user }),
    }),
  );
  await page.route("**/madira-api/auth/logout", (route) => {
    user = null;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });
  await page.route("https://lh3.googleusercontent.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: PNG }),
  );
}

test("login page renders configured, unconfigured, and a safe error", async ({ page }) => {
  fs.mkdirSync(OUT, { recursive: true });
  await mockAuth(page, { configured: true, user: null });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/login");
  await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
  await expect(page.getByTestId("mode-banner")).not.toContainText("connecting");
  const button = page.getByTestId("google-sign-in");
  await expect(button).toBeVisible();
  await expect(button).toHaveAttribute("href", "/madira-api/auth/google");
  await expect(button).toContainText("Continue with Google");
  await expect(page.locator("aside").getByTestId("sign-in-link")).toBeVisible();
  await page.screenshot({ path: path.join(OUT, "login-desktop.png"), fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(OUT, "login-mobile.png"), fullPage: true });

  await page.goto("/login?error=state");
  await expect(page.getByTestId("login-error")).toContainText(/expired/i);

  await page.goto("/login?error=%3Cscript%3Ealert(1)%3C/script%3E");
  await expect(page.getByTestId("login-page")).not.toContainText("<script>");
  await expect(page.getByTestId("login-error")).toContainText(/failed/i);

  await unmockAuth(page);
  await mockAuth(page, { configured: false, user: null });
  await page.goto("/login");
  await expect(page.getByTestId("login-unconfigured")).toContainText(/isn't configured/i);
  await expect(page.getByTestId("google-sign-in")).toHaveCount(0);
});

test("shell shows sign-in when signed out and the account when signed in", async ({ page }) => {
  fs.mkdirSync(OUT, { recursive: true });
  await mockAuth(page, {
    configured: true,
    user: { name: "Ada <img src=x onerror=alert(1)>", email: "ada@example.com", picture: "" },
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const aside = page.locator("aside");
  await expect(aside.getByTestId("account-name")).toHaveText("Ada <img src=x onerror=alert(1)>");
  await expect(aside.getByTestId("account-avatar")).toHaveText("A");
  await expect(aside.locator("img")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "The floor program, delegated." })).toBeVisible();

  await unmockAuth(page);
  await mockAuth(page, {
    configured: true,
    user: { name: "Ada Lovelace", email: "ada@example.com", picture: AVATAR },
  });
  await page.goto("/");
  await expect(aside.getByTestId("account-name")).toHaveText("Ada Lovelace");
  await expect(aside.getByTestId("account-avatar")).toHaveAttribute("src", AVATAR);
  await page.waitForFunction(() => {
    const img = document.querySelector("aside img[data-testid='account-avatar']") as HTMLImageElement | null;
    return !!img && img.complete && img.naturalWidth > 0;
  });
  await expect(aside.getByText("ada@example.com")).toBeVisible();
  await expect(page.getByTestId("mode-banner")).not.toContainText("connecting");
  await page.screenshot({ path: path.join(OUT, "sidebar-signed-in-desktop.png") });

  await aside.getByTestId("sign-out").click();
  await expect(aside.getByTestId("sign-in-link")).toBeVisible();
  await expect(aside.getByTestId("account-name")).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByTestId("mobile-menu")).toHaveCount(0);
  await page.getByRole("button", { name: "Sections" }).click();
  const menu = page.getByTestId("mobile-menu");
  await expect(menu.getByTestId("sign-in-link")).toBeVisible();

  await unmockAuth(page);
  await mockAuth(page, {
    configured: true,
    user: { name: "Ada Lovelace", email: "ada@example.com", picture: AVATAR },
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Sections" }).click();
  await expect(page.getByTestId("mobile-menu").getByTestId("account-name")).toHaveText("Ada Lovelace");
  await expect(page.getByTestId("mobile-menu").getByTestId("sign-out")).toBeVisible();
  await expect(page.getByTestId("mode-banner")).not.toContainText("connecting");
  await page.screenshot({ path: path.join(OUT, "sidebar-signed-in-mobile.png") });
});
