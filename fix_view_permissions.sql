-- Fix permissions for user_translation_stats view
-- This allows users to query their own stats without accessing auth.users directly

-- Drop the existing view
DROP VIEW IF EXISTS user_translation_stats CASCADE;

-- Recreate view WITHOUT the auth.users join (email not needed for stats)
-- The security_invoker option means the view uses the caller's permissions
-- This allows users to see only their own data based on the translations table RLS
CREATE OR REPLACE VIEW user_translation_stats
WITH (security_invoker = true)
AS
SELECT
    t.user_id,
    COUNT(*) as total_translations,
    SUM(t.total_tokens) as total_tokens_used,
    SUM(t.cost_total_usd) as total_cost_usd,
    MAX(t.created_at) as last_translation_at
FROM translations t
WHERE t.status = 'completed'
GROUP BY t.user_id;

-- Grant access to authenticated users
GRANT SELECT ON user_translation_stats TO authenticated, anon;
