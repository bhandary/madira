import { expect, test } from "@playwright/test";

test("a cross-origin write is rejected", async ({ request }) => {
  const blocked = await request.post("/madira-api/auth/logout", {
    headers: { Origin: "https://evil.example" },
  });
  expect(blocked.status()).toBe(403);
  const body = await blocked.json();
  expect(body.detail).toContain("blocked");
  expect(JSON.stringify(body)).not.toContain("https://evil.example");

  const allowed = await request.post("/madira-api/auth/logout");
  expect(allowed.ok()).toBeTruthy();

  const runtime = await request.post("/api/copilotkit", {
    headers: { Origin: "https://evil.example", "Content-Type": "application/json" },
    data: {},
  });
  expect(runtime.status()).toBe(403);
});
