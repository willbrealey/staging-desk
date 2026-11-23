CREATE ROLE desk_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE SCHEMA desk;
REVOKE ALL ON SCHEMA desk FROM PUBLIC;
GRANT USAGE ON SCHEMA desk TO desk_runtime;

CREATE TABLE desk.sessions (
    token_hash text PRIMARY KEY,
    tenant_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE FUNCTION desk.authenticate(token_digest text)
RETURNS TABLE (tenant_id uuid, actor_id uuid)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT tenant_id, actor_id FROM desk.sessions
    WHERE token_hash = token_digest AND expires_at > now()
$$;
REVOKE ALL ON FUNCTION desk.authenticate(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION desk.authenticate(text) TO desk_runtime;

CREATE TABLE desk.approvals (
    tenant_id uuid NOT NULL DEFAULT current_setting('desk.tenant')::uuid,
    id uuid NOT NULL,
    actor_id uuid NOT NULL DEFAULT current_setting('desk.actor')::uuid,
    case_id text NOT NULL CHECK (case_id = 'ready'),
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    decision text NOT NULL CHECK (decision IN ('approved', 'changes')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);
CREATE TABLE desk.audit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    approval_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    decision text NOT NULL,
    fingerprint text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, approval_id),
    FOREIGN KEY (tenant_id, approval_id) REFERENCES desk.approvals(tenant_id, id)
);
ALTER TABLE desk.approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE desk.approvals FORCE ROW LEVEL SECURITY;
CREATE POLICY approval_tenant ON desk.approvals TO desk_runtime
    USING (tenant_id = nullif(current_setting('desk.tenant', true), '')::uuid)
    WITH CHECK (
        tenant_id = nullif(current_setting('desk.tenant', true), '')::uuid
        AND actor_id = nullif(current_setting('desk.actor', true), '')::uuid
    );
ALTER TABLE desk.audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE desk.audit FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_tenant ON desk.audit TO desk_runtime
    USING (tenant_id = nullif(current_setting('desk.tenant', true), '')::uuid);
GRANT SELECT, INSERT ON desk.approvals TO desk_runtime;
GRANT SELECT ON desk.audit TO desk_runtime;

CREATE FUNCTION desk.record_decision() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    INSERT INTO desk.audit (tenant_id, approval_id, actor_id, decision, fingerprint)
    VALUES (NEW.tenant_id, NEW.id, NEW.actor_id, NEW.decision, NEW.fingerprint);
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION desk.record_decision() FROM PUBLIC;
CREATE TRIGGER audit_decision AFTER INSERT ON desk.approvals
    FOR EACH ROW EXECUTE FUNCTION desk.record_decision();
