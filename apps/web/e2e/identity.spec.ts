import { expect, test } from "@playwright/test";

const user = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "owner@example.test",
  status: "active",
  email_verified_at: "2026-07-16T12:00:00Z",
  is_platform_admin: false,
  display_name: "Owner Test",
};
const session = {
  id: "22222222-2222-4222-8222-222222222222",
  created_at: "2026-07-16T12:00:00Z",
  last_seen_at: "2026-07-16T12:00:00Z",
  expires_at: "2026-07-17T00:00:00Z",
  revoked_at: null,
  user_agent: "Playwright",
  active_tenant_id: "33333333-3333-4333-8333-333333333333",
  active_company_id: null,
  active_branch_id: null,
  current: true,
};
const me = {
  user,
  active_session: session,
  contexts: [
    {
      membership_id: "44444444-4444-4444-8444-444444444444",
      tenant_id: session.active_tenant_id,
      tenant_name: "Farmácia Teste",
      status: "active",
      companies: [],
    },
  ],
  permissions: [
    "tenant.read",
    "company.read",
    "branch.read",
    "user.read",
    "context.switch",
    "session.manage",
  ],
};

test("login establishes the application context and renders protected content", async ({
  page,
}) => {
  let authenticated = false;
  await page.route(/\/api\/v1\/me$/, async (route) => {
    if (!authenticated) {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "authentication_required",
            message: "Authentication required",
            details: {},
          },
        }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(me) });
  });
  await page.route(/\/api\/v1\/auth\/login$/, async (route) => {
    authenticated = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "Set-Cookie": "pharma_csrf=csrf-test; Path=/; SameSite=Lax" },
      body: JSON.stringify({ user, session, onboarding_required: false }),
    });
  });

  await page.goto("/login");
  await page.getByLabel("E-mail").fill(user.email);
  await page.getByLabel("Senha").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { name: "Olá, Owner Test" })).toBeVisible();
  await expect(page.getByText("Farmácia Teste").first()).toBeVisible();
  const permissionsMetric = page
    .getByRole("region", { name: "Resumo da identidade" })
    .locator("article")
    .filter({ hasText: "Permissões efetivas" });
  await expect(permissionsMetric.getByText("6", { exact: true })).toBeVisible();
});

test("registration displays a neutral verification response", async ({ page }) => {
  await page.route(/\/api\/v1\/me$/, (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "authentication_required", message: "Authentication required", details: {} },
      }),
    }),
  );
  await page.route(/\/api\/v1\/auth\/register$/, (route) =>
    route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ message: "accepted" }),
    }),
  );
  await page.goto("/register");
  await page.getByLabel("Nome").fill("New Owner");
  await page.getByLabel("E-mail profissional").fill("new@example.test");
  await page.getByLabel("Senha").fill("Very-Strong-Password-123");
  await page.getByRole("button", { name: "Criar conta" }).click();
  await expect(page.getByText("Confira seu e-mail para verificar a conta.")).toBeVisible();
});
