import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProtectedRoute } from "./protected-route";

const replace = vi.fn();
let authStatus = "loading";
vi.mock("next/navigation", () => ({ usePathname: () => "/app", useRouter: () => ({ replace }) }));
vi.mock("@/lib/auth/auth-context", () => ({
  useAuth: () => ({ status: authStatus, me: authStatus === "authenticated" ? {} : null }),
}));

describe("ProtectedRoute", () => {
  beforeEach(() => {
    replace.mockReset();
    authStatus = "loading";
  });
  it("renders a loading state while the session is checked", () => {
    render(
      <ProtectedRoute>
        <div>Secure</div>
      </ProtectedRoute>,
    );
    expect(screen.getByText("Validando sessão segura")).toBeInTheDocument();
  });
  it("redirects anonymous users to login", async () => {
    authStatus = "anonymous";
    render(
      <ProtectedRoute>
        <div>Secure</div>
      </ProtectedRoute>,
    );
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fapp"));
  });
  it("renders protected content for authenticated users", () => {
    authStatus = "authenticated";
    render(
      <ProtectedRoute>
        <div>Secure</div>
      </ProtectedRoute>,
    );
    expect(screen.getByText("Secure")).toBeInTheDocument();
  });
});
