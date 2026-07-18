import { expect, test, type Locator, type Page } from "@playwright/test";

const realStack = process.env.E2E_REAL_STACK === "1";
const email = process.env.E2E_ADMIN_EMAIL ?? "phase2-admin@example.com";
const password = process.env.E2E_ADMIN_PASSWORD ?? "Phase2-Only-Strong-Password-123";
const isolatedEmail = process.env.E2E_CROSS_TENANT_EMAIL ?? "phase2-isolated@example.com";
const isolatedPassword =
  process.env.E2E_CROSS_TENANT_PASSWORD ?? "Phase2-Isolated-Strong-Password-123";
const baseUrl = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const apiBaseUrl = process.env.E2E_API_BASE_URL ?? "http://localhost:8000/api/v1";

type BatchResponse = {
  id: string;
  state: string;
};

async function loginAndOnboard(
  page: Page,
  userEmail: string,
  userPassword: string,
  prefix: string,
): Promise<void> {
  page.setDefaultTimeout(15_000);
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(userEmail);
  await page.getByLabel("Senha").fill(userPassword);
  await page.getByRole("button", { name: "Entrar" }).click();

  await expect(page).toHaveURL(/\/(?:onboarding|app)$/);
  if (new URL(page.url()).pathname === "/onboarding") {
    await expect(
      page.getByRole("heading", { name: "Crie sua primeira organização" }),
    ).toBeVisible();
    const suffix = Date.now().toString();
    await page.getByLabel("Nome do tenant").fill(`${prefix} Tenant ${suffix}`);
    await page
      .getByLabel("Identificador do tenant")
      .fill(`${prefix.toLowerCase()}-tenant-${suffix}`);
    await page.getByLabel("Grupo econômico (opcional)").fill(`${prefix} Grupo ${suffix}`);
    await page.getByLabel("Razão social").fill(`${prefix} Inicial ${suffix} Ltda`);
    await page.getByLabel("Nome fantasia").fill(`${prefix} Inicial ${suffix}`);
    await page
      .getByLabel("Identificador da empresa")
      .fill(`${prefix.toLowerCase()}-inicial-${suffix}`);
    await page.getByLabel("Primeira filial").fill(`${prefix} Matriz ${suffix}`);
    await page
      .getByLabel("Identificador da filial")
      .fill(`${prefix.toLowerCase()}-matriz-${suffix}`);
    await page.getByLabel("Termos vigentes").selectOption({ index: 1 });
    await page.getByLabel(/Li e aceito/).check();
    await page.getByRole("button", { name: "Concluir onboarding" }).click();
  }
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { name: /Olá,/ })).toBeVisible();
}

async function createCompanyAndBranch(
  page: Page,
  prefix: string,
): Promise<{ company: string; branch: string }> {
  const suffix = Date.now().toString();
  const company = `${prefix} Empresa ${suffix}`;
  const branch = `${prefix} Filial ${suffix}`;

  await page.getByRole("link", { name: "Empresas" }).click();
  await page.getByLabel("Razão social").fill(`${company} Ltda`);
  await page.getByLabel("Nome fantasia").fill(company);
  await page.getByLabel("Identificador").fill(`${prefix.toLowerCase()}-empresa-${suffix}`);
  await page.getByRole("button", { name: "Criar empresa" }).click();
  await expect(page.getByRole("cell", { name: company, exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Filiais" }).click();
  await page.getByLabel("Empresa").selectOption({ label: company });
  await page.getByLabel("Nome da filial").fill(branch);
  await page.getByLabel("Identificador").fill(`${prefix.toLowerCase()}-filial-${suffix}`);
  await page.getByRole("button", { name: "Criar filial" }).click();
  await expect(page.getByText(branch)).toBeVisible();

  // A full navigation refreshes /me so the newly-created scope becomes selectable.
  await page.goto("/app/select-context");
  await page.getByLabel("Empresa (opcional)").selectOption({ label: company });
  await page.getByLabel("Filial (opcional)").selectOption({ label: branch });
  await page.getByRole("button", { name: "Aplicar contexto" }).click();
  await expect(page).toHaveURL(/\/app$/);

  return { company, branch };
}

async function waitForBatch(page: Page, batchId: string): Promise<void> {
  await expect
    .poll(
      async () => {
        const response = await page
          .context()
          .request.get(`${apiBaseUrl}/integrations/batches/${batchId}`);
        if (!response.ok()) return `http-${response.status()}`;
        return ((await response.json()) as BatchResponse).state;
      },
      { timeout: 60_000, intervals: [500, 1_000, 2_000] },
    )
    .toBe("completed");
}

async function synchronize(page: Page, sourceRow: Locator): Promise<string> {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/sync") &&
      response.status() === 200,
  );
  await sourceRow.getByRole("button", { name: "Sincronizar" }).click();
  const response = await responsePromise;
  const batch = (await response.json()) as BatchResponse;
  await waitForBatch(page, batch.id);
  await page.getByRole("button", { name: "Atualizar" }).click();
  return batch.id;
}

async function createSource(
  page: Page,
  sourceName: string,
  company: string,
  branch: string,
): Promise<Locator> {
  await page.getByRole("link", { name: "Integrações" }).click();
  await expect(page.getByRole("heading", { name: "Integrações ERP" })).toBeVisible();
  await page.getByLabel("Nome").fill(sourceName);
  await page
    .getByRole("combobox", { name: "Empresa", exact: true })
    .selectOption({ label: company });
  await page
    .getByRole("combobox", { name: "Filial", exact: true })
    .selectOption({ label: `${company} · ${branch}` });
  await page.getByLabel("Registros por domínio").fill("2");
  await page.getByRole("button", { name: "Criar fonte" }).click();

  const sourceRow = page.getByRole("row").filter({ hasText: sourceName });
  await expect(sourceRow).toBeVisible();
  await sourceRow.getByRole("button", { name: "Testar" }).click();
  await expect(sourceRow.getByText("healthy")).toBeVisible();
  return sourceRow;
}

test.describe("real Docker Compose canonical data stack", () => {
  test.skip(!realStack, "requires the Docker Compose stack and two regular users");
  test.setTimeout(240_000);

  test("processes, replays and isolates ERP data end to end", async ({ page, browser }) => {
    await loginAndOnboard(page, email, password, "Principal");
    const primary = await createCompanyAndBranch(page, "Principal");
    const primarySourceName = `ERP Principal ${Date.now()}`;
    const primarySourceRow = await createSource(
      page,
      primarySourceName,
      primary.company,
      primary.branch,
    );
    const primaryProductsBefore = await page.locator(".canonical-record").count();

    const firstBatchId = await synchronize(page, primarySourceRow);
    await expect(page.locator(".canonical-record")).toHaveCount(primaryProductsBefore + 2);

    const firstCompletedRow = page
      .locator("tbody tr")
      .filter({ has: page.locator(".batch-state-completed") })
      .first();
    await firstCompletedRow.getByRole("button", { name: "Detalhes" }).click();
    const detail = page.locator(".integration-detail");
    await expect(detail).toBeVisible();
    await expect(detail.getByRole("heading", { name: "Qualidade" })).toBeVisible();
    await expect(detail.locator(".quality-list li").first()).toBeVisible();
    await expect(detail.locator(".metric-card").filter({ hasText: "Recebidos" })).toContainText(
      "12",
    );
    await detail.getByRole("button", { name: "Fechar" }).click();

    // Byte-identical extraction: canonical upserts must preserve cardinality.
    await synchronize(page, primarySourceRow);
    await expect(page.locator(".canonical-record")).toHaveCount(primaryProductsBefore + 2);

    const reprocessResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith("/reprocess") &&
        response.status() === 200,
    );
    await page
      .locator("tbody tr")
      .filter({ has: page.locator(".batch-state-completed") })
      .first()
      .getByRole("button", { name: "Reprocessar" })
      .click();
    const reprocessed = (await (await reprocessResponsePromise).json()) as BatchResponse;
    await waitForBatch(page, reprocessed.id);
    await page.getByRole("button", { name: "Atualizar" }).click();
    await expect(page.locator(".canonical-record")).toHaveCount(primaryProductsBefore + 2);

    const isolatedContext = await browser.newContext({ baseURL: baseUrl });
    try {
      const isolatedPage = await isolatedContext.newPage();
      await loginAndOnboard(isolatedPage, isolatedEmail, isolatedPassword, "Isolado");
      const isolated = await createCompanyAndBranch(isolatedPage, "Isolado");
      const isolatedSourceName = `ERP Isolado ${Date.now()}`;
      const isolatedSourceRow = await createSource(
        isolatedPage,
        isolatedSourceName,
        isolated.company,
        isolated.branch,
      );
      const isolatedProductsBefore = await isolatedPage.locator(".canonical-record").count();
      const isolatedBatchId = await synchronize(isolatedPage, isolatedSourceRow);
      await expect(isolatedPage.locator(".canonical-record")).toHaveCount(
        isolatedProductsBefore + 2,
      );

      const primaryCannotReadIsolated = await page
        .context()
        .request.get(`${apiBaseUrl}/integrations/batches/${isolatedBatchId}`);
      expect(primaryCannotReadIsolated.status()).toBe(404);

      const isolatedCannotReadPrimary = await isolatedContext.request.get(
        `${apiBaseUrl}/integrations/batches/${firstBatchId}`,
      );
      expect(isolatedCannotReadPrimary.status()).toBe(404);

      const primarySources = await page
        .context()
        .request.get(`${apiBaseUrl}/integrations/sources?limit=100&offset=0`);
      expect(primarySources.ok()).toBe(true);
      expect(await primarySources.text()).not.toContain(isolatedSourceName);
    } finally {
      await isolatedContext.close();
    }

    await page.getByRole("button", { name: "Sair" }).click();
    await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Fintegrations$/);
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login\?next=/);
  });
});
