import { expect, test } from "@playwright/test";

const realStack = process.env.E2E_REAL_STACK === "1";
const email = process.env.E2E_ADMIN_EMAIL ?? "phase2-admin@example.test";
const password = process.env.E2E_ADMIN_PASSWORD ?? "Phase2-Only-Strong-Password-123";

test.describe("real Docker Compose identity stack", () => {
  test.skip(!realStack, "requires the Docker Compose stack and bootstrapped administrator");

  test("login, onboarding, organization creation, context and logout work end to end", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByLabel("E-mail").fill(email);
    await page.getByLabel("Senha").fill(password);
    await page.getByRole("button", { name: "Entrar" }).click();

    await expect(page).toHaveURL(/\/onboarding$/);
    await expect(
      page.getByRole("heading", { name: "Crie sua primeira organização" }),
    ).toBeVisible();

    const suffix = Date.now().toString();
    await page.getByLabel("Nome do tenant").fill(`Tenant E2E ${suffix}`);
    await page.getByLabel("Identificador do tenant").fill(`tenant-e2e-${suffix}`);
    await page.getByLabel("Grupo econômico (opcional)").fill(`Grupo E2E ${suffix}`);
    await page.getByLabel("Razão social").fill(`Farmácia E2E ${suffix} Ltda`);
    await page.getByLabel("Nome fantasia").fill(`Farmácia E2E ${suffix}`);
    await page.getByLabel("Identificador da empresa").fill(`farmacia-e2e-${suffix}`);
    await page.getByLabel("Primeira filial").fill(`Matriz E2E ${suffix}`);
    await page.getByLabel("Identificador da filial").fill(`matriz-e2e-${suffix}`);
    await page.getByLabel("Termos vigentes").selectOption({ index: 1 });
    await page.getByLabel(/Li e aceito/).check();
    await page.getByRole("button", { name: "Concluir onboarding" }).click();

    await expect(page).toHaveURL(/\/app$/);
    await expect(page.getByRole("heading", { name: /Olá,/ })).toBeVisible();
    await expect(page.getByText(`Tenant E2E ${suffix}`).first()).toBeVisible();

    await page.getByRole("link", { name: "Empresas" }).click();
    await page.getByLabel("Razão social").fill(`Segunda Empresa ${suffix} Ltda`);
    await page.getByLabel("Nome fantasia").fill(`Segunda Empresa ${suffix}`);
    await page.getByLabel("Identificador").fill(`segunda-empresa-${suffix}`);
    await page.getByRole("button", { name: "Criar empresa" }).click();
    await expect(page.getByText(`Segunda Empresa ${suffix}`)).toBeVisible();

    await page.getByRole("link", { name: "Filiais" }).click();
    await page.getByLabel("Empresa").selectOption({ label: `Segunda Empresa ${suffix}` });
    await page.getByLabel("Nome da filial").fill(`Filial E2E ${suffix}`);
    await page.getByLabel("Identificador").fill(`filial-e2e-${suffix}`);
    await page.getByRole("button", { name: "Criar filial" }).click();
    await expect(page.getByText(`Filial E2E ${suffix}`)).toBeVisible();

    await page.getByRole("button", { name: "Sair" }).click();
    await expect(page).toHaveURL(/\/login$/);
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login\?next=/);
  });
});
