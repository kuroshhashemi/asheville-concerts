BEGIN;
CREATE TABLE IF NOT EXISTS public.app_login_attempts (
 attempt_id uuid PRIMARY KEY,
 started_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz,
 outcome text NOT NULL DEFAULT 'started' CHECK(outcome IN ('started','success','error')),
 user_id text, email text, first_sign_in boolean NOT NULL DEFAULT false,
 error_code text,
 is_test boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS app_login_attempts_started ON public.app_login_attempts(started_at DESC);
CREATE TABLE IF NOT EXISTS public.app_auth_alerts(kind text PRIMARY KEY,sent_at timestamptz NOT NULL DEFAULT now());
ALTER TABLE public.app_login_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_auth_alerts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.app_login_attempts, public.app_auth_alerts FROM anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.app_login_attempts,public.app_auth_alerts TO service_role;
COMMIT;
SELECT relname,relrowsecurity AS rls_enabled,has_table_privilege('anon',oid,'SELECT') AS anonymous_read
FROM pg_class WHERE oid IN ('public.app_login_attempts'::regclass,'public.app_auth_alerts'::regclass);
