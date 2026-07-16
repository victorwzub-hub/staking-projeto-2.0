import { expect, test } from "@playwright/test";

test("shows loading and then the real API health contract", async ({ page }) => {
  let releaseHealthResponse!: () => void;
  const responseGate = new Promise<void>((resolve) => {
    releaseHealthResponse = resolve;
  });

  await page.route(/\/api\/v1\/health$/, async (route) => {
    await responseGate;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: {
        "Access-Control-Allow-Origin": "*",
        "X-Correlation-ID": "playwright-health-check",
      },
      body: JSON.stringify({ status: "ok", service: "Pharma Intelligence SaaS", version: "0.2.0" }),
    });
  });
  await page.route(/\/api\/v1\/me$/, (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "authentication_required", message: "Authentication required", details: {} },
      }),
    }),
  );

  const healthRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/health"));
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Identidade e acesso preparados",
  );
  await expect(page.getByText("Verificando conexão com a API")).toBeVisible();
  await healthRequest;
  releaseHealthResponse();
  await expect(page.getByText("API disponível")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Pharma Intelligence SaaS")).toBeVisible();
  await expect(page.getByText("0.2.0")).toBeVisible();
});
