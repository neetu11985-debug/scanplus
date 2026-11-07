-- Apply only after verifying the exact Neon project/branch and reviewing the plan.
-- Use DATABASE_URL_UNPOOLED. The runner wraps this file in one transaction.
-- No legacy plaintext sessions or reports are imported.
CREATE SCHEMA IF NOT EXISTS scanplus;
REVOKE ALL ON SCHEMA scanplus FROM PUBLIC;
CREATE TABLE IF NOT EXISTS scanplus.encrypted_records (
    purpose TEXT NOT NULL,
    id TEXT PRIMARY KEY,
    version INTEGER NOT NULL CHECK (version > 0),
    lookup BYTEA NOT NULL CHECK (octet_length(lookup) = 32),
    nonce BYTEA NOT NULL CHECK (octet_length(nonce) = 12),
    ciphertext BYTEA NOT NULL,
    UNIQUE (purpose, lookup)
);
REVOKE ALL ON TABLE scanplus.encrypted_records FROM PUBLIC;
CREATE INDEX IF NOT EXISTS encrypted_records_key_version ON scanplus.encrypted_records (version);
