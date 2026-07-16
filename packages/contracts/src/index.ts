export type ApiErrorDetails = Record<string, unknown> | unknown[];

export type ApiErrorResponse = {
  error: {
    code: string;
    message: string;
    details: ApiErrorDetails;
  };
};

export type MessageResponse = { message: string };

export type DependencyStatus = {
  status: "ok" | "error";
  detail: string | null;
};

export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
};

export type ReadinessResponse = {
  status: "ready" | "not_ready";
  checks: Record<string, DependencyStatus>;
};

export type User = {
  id: string;
  email: string;
  status: string;
  email_verified_at: string | null;
  is_platform_admin: boolean;
  display_name: string | null;
};

export type Session = {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  revoked_at: string | null;
  user_agent: string | null;
  active_tenant_id: string | null;
  active_company_id: string | null;
  active_branch_id: string | null;
  current: boolean;
};

export type BranchContext = { id: string; name: string };
export type CompanyContext = { id: string; name: string; branches: BranchContext[] };
export type MembershipContext = {
  membership_id: string;
  tenant_id: string;
  tenant_name: string;
  status: string;
  companies: CompanyContext[];
};

export type MeResponse = {
  user: User;
  active_session: Session;
  contexts: MembershipContext[];
  permissions: string[];
};

export type LoginResponse = {
  user: User;
  session: Session;
  onboarding_required: boolean;
};

export type OnboardingProgress = {
  status: string;
  current_step: string;
  tenant_id: string | null;
  data: Record<string, string>;
};

export type TermsVersion = {
  id: string;
  document_type: string;
  version: string;
};

export type Tenant = {
  id: string;
  name: string;
  slug: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type EconomicGroup = {
  id: string;
  tenant_id: string;
  name: string;
  status: string;
  version: number;
};

export type Company = {
  id: string;
  tenant_id: string;
  economic_group_id: string | null;
  legal_name: string;
  trade_name: string;
  slug: string;
  status: string;
  version: number;
};

export type Branch = {
  id: string;
  tenant_id: string;
  company_id: string;
  name: string;
  slug: string;
  status: string;
  version: number;
};

export type Membership = {
  id: string;
  tenant_id: string;
  user_id: string;
  email: string;
  display_name: string;
  status: string;
  title: string | null;
  roles: string[];
  version: number;
};

export type Invitation = {
  id: string;
  tenant_id: string;
  normalized_email: string;
  role_id: string;
  company_id: string | null;
  branch_id: string | null;
  status: string;
  expires_at: string;
  created_at: string;
};

export type Team = {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  version: number;
};

export type Permission = {
  id: string;
  key: string;
  scope: string;
  description: string;
  catalog_version: number;
};

export type Role = {
  id: string;
  tenant_id: string | null;
  name: string;
  slug: string;
  scope: string;
  is_system: boolean;
  is_editable: boolean;
  version: number;
  permissions: string[];
};

export type AuditEvent = {
  id: string;
  actor_user_id: string | null;
  effective_user_id: string | null;
  tenant_id: string | null;
  company_id: string | null;
  branch_id: string | null;
  action: string;
  category: string;
  resource_type: string | null;
  resource_id: string | null;
  outcome: string;
  correlation_id: string | null;
  changed_fields: string[];
  justification: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type Profile = {
  user_id: string;
  display_name: string;
  locale: string;
  timezone: string;
  version: number;
};

export type SecurityEvent = {
  id: string;
  event_type: string;
  outcome: string;
  correlation_id: string | null;
  user_agent: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type PlatformUser = {
  id: string;
  email: string;
  display_name: string;
  status: string;
  email_verified_at: string | null;
  is_platform_admin: boolean;
  version: number;
  created_at: string;
};

export type RoleAssignment = {
  id: string;
  tenant_id: string;
  membership_id: string;
  role_id: string;
  company_id: string | null;
  branch_id: string | null;
  assigned_by_user_id: string;
};
