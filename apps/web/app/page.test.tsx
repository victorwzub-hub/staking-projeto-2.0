import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import HomePage from "./page";

vi.mock("@/components/api-status", () => ({
  ApiStatus: () => <div>API status component</div>,
}));

describe("HomePage", () => {
  it("identifies the delivery as technical foundation only", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Base pronta para evoluir com segurança.",
    );
    expect(screen.getByText(/Autenticação, billing, dashboards/)).toBeInTheDocument();
    expect(screen.getByText("API status component")).toBeInTheDocument();
  });
});
