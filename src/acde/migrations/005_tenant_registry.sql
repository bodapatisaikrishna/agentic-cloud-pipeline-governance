-- D-097: the tenant registry D-085 named as the missing piece for a real multi-tenant SaaS layer
-- ("a tenant registry, per-request tenant resolution, or any routing that lets one database serve
-- multiple tenants" -- none of which existed before this). Admin-provisioned only: no public
-- signup, no billing -- an operator creates a tenant via `acde tenants create` or `POST /tenants`.

CREATE TABLE IF NOT EXISTS control.tenants (
  tenant_id    TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
  created_ts   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every existing deployment's rows are already tagged tenant_id='default' (D-085's own default);
-- this gives them a matching registry row with zero manual step on upgrade.
INSERT INTO control.tenants (tenant_id, display_name, status)
VALUES ('default', 'Default Tenant', 'active')
ON CONFLICT (tenant_id) DO NOTHING;
