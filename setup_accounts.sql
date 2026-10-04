-- Server-only table. Google identity is verified by Streamlit; the server sets user_id.
CREATE TABLE IF NOT EXISTS public.user_show_statuses (
  user_id text NOT NULL,
  show_key text NOT NULL,
  status text NOT NULL CHECK (status IN ('Unread','Pass','Interested','Going')),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id,show_key)
);
ALTER TABLE public.user_show_statuses ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.user_show_statuses FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.user_show_statuses TO service_role;
-- No browser API policies: only our server secret can access this table.
CREATE TABLE IF NOT EXISTS public.user_filter_settings (
 user_id text PRIMARY KEY,
 preferences jsonb NOT NULL DEFAULT '{}',
 updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.user_filter_settings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.user_filter_settings FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.user_filter_settings TO service_role;
