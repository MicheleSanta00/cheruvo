-- 008_enable_rls_all.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- Chiude il buco segnalato da Supabase ("Table publicly accessible"):
-- abilita Row-Level Security su TUTTE le tabelle dello schema public.
--
-- Perché è sicuro e non rompe niente:
--   • Il backend si connette come ruolo `postgres`, PROPRIETARIO delle tabelle.
--     In PostgreSQL il proprietario bypassa la RLS (finché non si usa FORCE),
--     quindi il backend continua a leggere/scrivere tutto come prima.
--   • Il frontend, tramite la chiave pubblica (anon/authenticated), accede
--     DIRETTAMENTE solo a `watchlist`, che ha già le sue policy (migration 002).
--     Tutte le altre tabelle il frontend le raggiunge via backend, quindi
--     "nessuna policy = nessun accesso diretto" è esattamente ciò che vogliamo.
--
-- NB: si usa ENABLE (non FORCE) proprio per lasciare il bypass al proprietario.
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT tablename
    FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename <> 'watchlist'   -- già protetta con policy proprie (frontend vi accede diretto)
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', r.tablename);
  END LOOP;
END $$;

-- Verifica (opzionale): elenca eventuali tabelle public ancora senza RLS.
-- Dopo questa migration deve restituire solo 'watchlist' (o nulla).
--   SELECT tablename FROM pg_tables t
--   WHERE schemaname = 'public'
--     AND NOT EXISTS (
--       SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
--       WHERE n.nspname = 'public' AND c.relname = t.tablename AND c.relrowsecurity
--     );
