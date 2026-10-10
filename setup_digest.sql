-- Private, server-only subscriptions and duplicate-send protection.
CREATE TABLE IF NOT EXISTS public.email_subscriptions (
 subscription_id uuid PRIMARY KEY,
 email text UNIQUE NOT NULL,
 user_id text,
 enabled boolean NOT NULL DEFAULT false,
 unsubscribe_token text UNIQUE NOT NULL CHECK (length(unsubscribe_token) >= 32),
 subscribed_at timestamptz NOT NULL DEFAULT now(),
 last_processed_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.email_subscriptions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.email_subscriptions FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.email_subscriptions TO service_role;

CREATE TABLE IF NOT EXISTS public.email_digest_deliveries (
 subscription_id uuid NOT NULL REFERENCES public.email_subscriptions(subscription_id),
 period_end timestamptz NOT NULL,
 status text NOT NULL CHECK (status IN ('sending','sent','empty','failed','uncertain')),
 show_keys jsonb NOT NULL DEFAULT '[]',
 attempted_at timestamptz NOT NULL DEFAULT now(),
 sent_at timestamptz,
 message_id text,
 PRIMARY KEY (subscription_id,period_end)
);
ALTER TABLE public.email_digest_deliveries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.email_digest_deliveries FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.email_digest_deliveries TO service_role;
