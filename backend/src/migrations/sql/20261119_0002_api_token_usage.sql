-- Migration: API & LLM Token Usage Tracking
-- Tracks token consumption per user, provider, model, and feature with estimated USD cost.

CREATE TABLE IF NOT EXISTS "api_token_usages" (
    "id" VARCHAR(80) NOT NULL PRIMARY KEY,
    "user_id" VARCHAR(255) NOT NULL,
    "provider" VARCHAR(50) NOT NULL,
    "model" VARCHAR(100) NOT NULL,
    "feature" VARCHAR(50) NOT NULL,
    "input_tokens" INTEGER NOT NULL DEFAULT 0,
    "output_tokens" INTEGER NOT NULL DEFAULT 0,
    "total_tokens" INTEGER NOT NULL DEFAULT 0,
    "cost_usd" NUMERIC(10, 6) NOT NULL DEFAULT 0.000000,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS "idx_api_token_usages_user_id" ON "api_token_usages"("user_id");
CREATE INDEX IF NOT EXISTS "idx_api_token_usages_created_at" ON "api_token_usages"("created_at");
CREATE INDEX IF NOT EXISTS "idx_api_token_usages_provider" ON "api_token_usages"("provider");
CREATE INDEX IF NOT EXISTS "idx_api_token_usages_feature" ON "api_token_usages"("feature");
