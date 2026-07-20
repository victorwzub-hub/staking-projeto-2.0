import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "./page";

const replace = vi.fn();
const refresh = vi.fn();
const apiJson = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/auth/auth-context", () => ({ useAuth: () => ({ refresh }) }));
vi.mock("@/lib/http/client", () => ({ apiJson: (...args: unknown[]) => apiJson(...args) }));

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("submits credentials and redirects to onboarding when required", async () => {
    apiJson.mockResolvedValue({ onboarding_required: true });
    refresh.mockResolvedValue(null);
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "owner@example.com" } });
    fireEvent.change(screen.getByLabelText("Senha"), {
      target: { value: "correct horse battery staple" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() =>
      expect(apiJson).toHaveBeenCalledWith("auth/login", "POST", {
        email: "owner@example.com",
        password: "correct horse battery staple",
      }),
    );
    expect(refresh).toHaveBeenCalled();
    expect(replace).toHaveBeenCalledWith("/onboarding");
  });

  it("shows a backend error without redirecting", async () => {
    apiJson.mockRejectedValue(new Error("Credenciais inválidas"));
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "user@example.com" } });
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByText("Credenciais inválidas")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
