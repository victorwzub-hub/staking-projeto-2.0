import { expect, test } from "@playwright/test";

test("shows loading and then the API health response", async ({ page }) => {
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
      body: JSON.stringify({
        status: "ok",
        service: "Pharma Intelligence SaaS",
        version: "0.1.1",
      }),
    });
  });

  const healthRequest = page.waitForRequest((request) =>
    request.url().endsWith("/api/v1/health"),
  );

  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Base pronta para evoluir com segurança.",
  );

  await expect(page.getByText("Verificando conexão com a API")).toBeVisible();

  // Confirma que o JavaScript foi hidratado e que a chamada realmente começou.
  await healthRequest;

  releaseHealthResponse();

  await expect(page.getByText("API disponível")).toBeVisible({
    timeout: 15_000,
  });

  await expect(page.getByText("Pharma Intelligence SaaS")).toBeVisible();
  await expect(page.getByText("0.1.1")).toBeVisible();
});