import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import HomePage from "./page";

vi.mock("@/components/api-status", () => ({
  ApiStatus: () => <div>API status component</div>,
}));

describe("HomePage", () => {
  it("describes the implemented identity and multi-tenant foundation", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Identidade e acesso preparados para um SaaS de alta criticidade.",
    );
    expect(
      screen.getByText(/Os módulos analíticos de farmácia permanecem fora/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Iniciar onboarding" })).toHaveAttribute(
      "href",
      "/register",
    );
    expect(screen.getByText("API status component")).toBeInTheDocument();
  });
});
