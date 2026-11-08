-- Prepared only. Apply to the exact approved Neon project in one transaction
-- after owner review. This adds a separate non-personal allowance ledger.
-- No existing table, row, encryption key or permission is changed.
BEGIN;
CREATE SCHEMA IF NOT EXISTS scanplus;
CREATE TABLE scanplus.owner_test_allowances (
    run_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    sms_used INTEGER NOT NULL DEFAULT 0 CHECK (sms_used BETWEEN 0 AND 1),
    checks_used INTEGER NOT NULL DEFAULT 0 CHECK (checks_used BETWEEN 0 AND 5),
    searches_used INTEGER NOT NULL DEFAULT 0 CHECK (searches_used BETWEEN 0 AND 3),
    CHECK (expires_at > created_at AND expires_at <= created_at + INTERVAL '24 hours')
);
REVOKE ALL ON TABLE scanplus.owner_test_allowances FROM PUBLIC;

-- The app role receives EXECUTE only, never INSERT/UPDATE/DELETE on this table.
-- A fixed search_path and fully qualified table prevent name substitution.
CREATE FUNCTION scanplus.consume_owner_test_allowance(p_run UUID, p_kind TEXT)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    allowance scanplus.owner_test_allowances%ROWTYPE;
    used INTEGER;
BEGIN
    IF p_kind NOT IN ('sms', 'checks', 'searches') OR p_kind IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT * INTO allowance FROM scanplus.owner_test_allowances
        WHERE run_id = p_run FOR UPDATE;
    IF NOT FOUND OR NOT allowance.enabled OR allowance.expires_at <= clock_timestamp() THEN
        RETURN NULL;
    END IF;
    IF p_kind = 'sms' AND allowance.sms_used < 1 THEN
        UPDATE scanplus.owner_test_allowances SET sms_used = sms_used + 1
            WHERE run_id = p_run RETURNING sms_used INTO used;
    ELSIF p_kind = 'checks' AND allowance.checks_used < 5 THEN
        UPDATE scanplus.owner_test_allowances SET checks_used = checks_used + 1
            WHERE run_id = p_run RETURNING checks_used INTO used;
    ELSIF p_kind = 'searches' AND allowance.searches_used < 3 THEN
        UPDATE scanplus.owner_test_allowances SET searches_used = searches_used + 1
            WHERE run_id = p_run RETURNING searches_used INTO used;
    ELSE
        RETURN NULL;
    END IF;
    RETURN used;
END;
$$;
REVOKE ALL ON FUNCTION scanplus.consume_owner_test_allowance(UUID, TEXT) FROM PUBLIC;
-- Owner setup, separately authorized: grant the dedicated application role USAGE
-- on schema scanplus and EXECUTE on the function above. Do not grant table writes.
-- Do not create a fixture or live run grant from application startup or migration.

COMMIT;
