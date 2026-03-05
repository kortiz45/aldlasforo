-- Aldlas / Supabase Postgres schema
-- Ejecutar en Supabase SQL Editor

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    username_lower TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'user',
    plan VARCHAR(32) NOT NULL DEFAULT 'free',
    status VARCHAR(32) NOT NULL DEFAULT 'Activo',
    is_vip BOOLEAN NOT NULL DEFAULT FALSE,
    expiry_date DATE NULL,
    device_lock TEXT NULL,
    daily_credits_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wallets (
    username_lower TEXT PRIMARY KEY,
    balance BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT wallets_balance_nonnegative CHECK (balance >= 0),
    CONSTRAINT wallets_user_fk FOREIGN KEY (username_lower) REFERENCES users(username_lower) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gifts (
    code TEXT PRIMARY KEY,
    kind VARCHAR(32) NOT NULL,
    plan VARCHAR(32) NOT NULL DEFAULT 'vip',
    days INTEGER NOT NULL DEFAULT 30,
    credits BIGINT NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    used_at TIMESTAMPTZ NULL,
    used_by TEXT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS media_assets (
    id BIGSERIAL PRIMARY KEY,
    object_key TEXT NOT NULL,
    public_url TEXT NOT NULL,
    media_kind VARCHAR(12) NOT NULL,
    mime_type VARCHAR(120) NOT NULL,
    size_bytes BIGINT NOT NULL,
    storage_provider VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username_lower ON users (username_lower);
CREATE INDEX IF NOT EXISTS idx_gifts_status ON gifts (status);
CREATE INDEX IF NOT EXISTS idx_media_assets_created_at ON media_assets (created_at DESC);
