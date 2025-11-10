-- PDF Translation App Database Schema for Supabase
-- This schema tracks all translation jobs and user activity

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create translations table
CREATE TABLE IF NOT EXISTS translations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- File information
    original_filename TEXT NOT NULL,
    translated_filename TEXT NOT NULL,
    file_size_bytes INTEGER,

    -- Translation metadata
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER GENERATED ALWAYS AS (input_tokens + output_tokens) STORED,

    -- Cost tracking (Haiku 4.5 pricing: $0.80/1M input, $4.00/1M output)
    cost_input_usd DECIMAL(10, 4) GENERATED ALWAYS AS ((input_tokens::DECIMAL / 1000000) * 0.80) STORED,
    cost_output_usd DECIMAL(10, 4) GENERATED ALWAYS AS ((output_tokens::DECIMAL / 1000000) * 4.00) STORED,
    cost_total_usd DECIMAL(10, 4) GENERATED ALWAYS AS (
        ((input_tokens::DECIMAL / 1000000) * 0.80) +
        ((output_tokens::DECIMAL / 1000000) * 4.00)
    ) STORED,

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Indexes for performance
    CONSTRAINT translations_user_id_created_at_idx CHECK (true)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_translations_user_id ON translations(user_id);
CREATE INDEX IF NOT EXISTS idx_translations_created_at ON translations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_translations_status ON translations(status);

-- Enable Row Level Security (RLS)
ALTER TABLE translations ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Users can only see their own translations
CREATE POLICY "Users can view their own translations"
    ON translations
    FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own translations"
    ON translations
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own translations"
    ON translations
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own translations"
    ON translations
    FOR DELETE
    USING (auth.uid() = user_id);

-- Create a view for translation statistics per user
CREATE OR REPLACE VIEW user_translation_stats AS
SELECT
    t.user_id,
    u.email as user_email,
    COUNT(*) as total_translations,
    SUM(t.total_tokens) as total_tokens_used,
    SUM(t.cost_total_usd) as total_cost_usd,
    MAX(t.created_at) as last_translation_at
FROM translations t
LEFT JOIN auth.users u ON t.user_id = u.id
WHERE t.status = 'completed'
GROUP BY t.user_id, u.email;

-- Grant access to the view
GRANT SELECT ON user_translation_stats TO authenticated;

-- RLS for the view
ALTER VIEW user_translation_stats SET (security_invoker = true);
