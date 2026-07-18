export type ApiErrorDetails = Record<string, unknown> | unknown[];

export type ApiErrorResponse = {
  error: {
    code: string;
    message: string;
    details: ApiErrorDetails;
  };
};

export type MessageResponse = { message: string };

export type AnalyticsKpiResult = {
  code: string;
  name: string;
  category: string;
  unit: string;
  value: string | null;
  reason: string | null;
  formula_version: number;
  period_start: string;
  period_end: string;
  comparison_value: string | null;
  absolute_variation: string | null;
  percentage_variation: string | null;
  target_value: string | null;
  target_status: string | null;
  freshness_at: string | null;
  quality_score: string | null;
  data_version: number;
  cache_status: "hit" | "miss" | "bypass";
};

export type AnalyticsKpiComparison = AnalyticsKpiResult & {
  same_period_last_year_value: string | null;
  moving_average_28d_value: string | null;
  authorized_network_value: string | null;
  category_value: string | null;
};

export type AnalyticsTimePoint = {
  period: string;
  value: string | null;
  comparison_value: string | null;
  target_value: string | null;
};

export type AnalyticsRankingItem = {
  dimension_key: string;
  label: string;
  value: string | null;
  share_percent: string | null;
  rank: number;
};

export type AnalyticsDrillDownItem = {
  fact_id: string;
  fact_type: string;
  occurred_at: string;
  company_id: string | null;
  branch_id: string | null;
  product_id: string | null;
  supplier_id: string | null;
  canonical_table: string;
  canonical_record_id: string;
  canonical_version: string;
  measures: Record<string, unknown>;
  source_batch_id: string | null;
  transformation_version: string | null;
};

export type AnalyticsAvailableFilters = {
  economic_groups: Array<{ id: string; label: string }>;
  companies: Array<{ id: string; label: string }>;
  branches: Array<{ id: string; label: string }>;
  products: Array<{ id: string; label: string }>;
  categories: Array<{ id: string; label: string }>;
  brands: Array<{ id: string; label: string }>;
  suppliers: Array<{ id: string; label: string }>;
  channels: string[];
  minimum_date: string | null;
  maximum_date: string | null;
};

export type AnalyticsFreshness = {
  data_version: number;
  watermark: string | null;
  freshness_at: string | null;
  lag_seconds: number | null;
  quality_score: string | null;
  last_refresh_job_id: string | null;
};

export type AnalyticsGoal = {
  id: string;
  tenant_id: string;
  company_id: string | null;
  branch_id: string | null;
  kpi_code: string;
  period_start: string;
  period_end: string;
  target_value: string | null;
  lower_value: string | null;
  upper_value: string | null;
  direction: "increase" | "decrease" | "target";
  owner_user_id: string;
  note: string | null;
  active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
};

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
export type CompanyContext = {
  id: string;
  name: string;
  branches: BranchContext[];
};
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

export type CursorPage<T> = {
  items: T[];
  next_cursor: string | null;
  limit: number;
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

export type ConnectorType = {
  key: string;
  name: string;
  version: string;
  schema_version: string;
  capabilities: string[];
  authentication_types: string[];
  supported_entities: string[];
  status: string;
};

export type DataSource = {
  id: string;
  tenant_id: string;
  company_id: string;
  branch_id: string | null;
  connector_key: string;
  connector_version: string;
  name: string;
  dataset_type: string;
  status: string;
  sync_mode: string;
  schedule_cron: string | null;
  last_sync_at: string | null;
  next_sync_at: string | null;
  last_health_status: string | null;
  last_health_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type ImportBatch = {
  id: string;
  tenant_id: string;
  company_id: string;
  branch_id: string | null;
  data_source_id: string;
  parent_batch_id: string | null;
  dataset_type: string;
  period_start: string | null;
  period_end: string | null;
  state: string;
  progress_percent: number;
  received_records: number;
  valid_records: number;
  rejected_records: number;
  duplicate_records: number;
  cancel_requested: boolean;
  correlation_id: string | null;
  queued_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
};

export type ProcessingError = {
  id: string;
  batch_id: string;
  staging_record_id: string | null;
  step_name: string;
  entity_type: string | null;
  field_name: string | null;
  error_class: string;
  error_code: string;
  severity: string;
  message: string;
  retryable: boolean;
  created_at: string;
};

export type QualityResult = {
  id: string;
  batch_id: string;
  entity_type: string;
  rule_key: string;
  severity: string;
  evaluated_records: number;
  failed_records: number;
  score: number;
  details: Record<string, unknown>;
  created_at: string;
};

export type MappingField = {
  source_field: string;
  target_entity: string;
  target_field: string;
  transform_type: string;
  transform_config: Record<string, unknown>;
  required: boolean;
  default_value: string | null;
};

export type MappingProfile = {
  id: string;
  version_id: string;
  data_source_id: string;
  name: string;
  dataset_type: string;
  version_number: number;
  status: string;
  fields: MappingField[];
};

export type IntegrationObservability = {
  syncs_started: number;
  syncs_completed: number;
  syncs_failed: number;
  backlog: number;
  dead_letters: number;
  records_received: number;
  records_valid: number;
  records_rejected: number;
  records_duplicate: number;
  storage_bytes: number;
  average_records_per_second: number | null;
  average_quality_score: number | null;
};
