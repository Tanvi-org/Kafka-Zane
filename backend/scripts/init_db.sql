-- Source of truth: which GitHub App installation belongs to which tenant
CREATE TABLE IF NOT EXISTS github_installations (
    installation_id BIGINT PRIMARY KEY,
    tenant_id UUID NOT NULL
);

-- POC seed: replace with your real installation id from GitHub webhook payload
INSERT INTO github_installations (installation_id, tenant_id)
VALUES (12345678, 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
ON CONFLICT (installation_id) DO NOTHING;
