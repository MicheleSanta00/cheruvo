-- ============================================================
-- Migration 002: Watchlist RLS + limite free tier
-- Eseguire in Supabase SQL Editor
-- ============================================================


-- 1. ABILITA RLS sulla tabella watchlist
-- (senza RLS qualsiasi utente autenticato può leggere tutti i record)
ALTER TABLE watchlist ENABLE ROW LEVEL SECURITY;


-- 2. POLICY: ogni utente vede solo la propria watchlist
CREATE POLICY "watchlist_select_own"
  ON watchlist FOR SELECT
  USING (auth.uid() = user_id);


-- 3. POLICY: ogni utente può inserire solo per se stesso
CREATE POLICY "watchlist_insert_own"
  ON watchlist FOR INSERT
  WITH CHECK (auth.uid() = user_id);


-- 4. POLICY: ogni utente può eliminare solo i propri ticker
CREATE POLICY "watchlist_delete_own"
  ON watchlist FOR DELETE
  USING (auth.uid() = user_id);


-- 5. FUNZIONE: controlla il limite watchlist prima di ogni INSERT
--    - Utenti PRO: nessun limite
--    - Utenti free / non registrati: max 3 ticker
CREATE OR REPLACE FUNCTION check_watchlist_limit()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER   -- eseguita con i permessi del proprietario, non dell'utente
AS $$
DECLARE
  v_status      TEXT;
  v_count       INT;
  FREE_LIMIT    CONSTANT INT := 3;
BEGIN
  -- Leggi lo stato subscription dell'utente
  SELECT status INTO v_status
  FROM subscriptions
  WHERE user_id = NEW.user_id;

  -- PRO (e past_due che non è ancora scaduto): nessun limite
  IF v_status = 'pro' THEN
    RETURN NEW;
  END IF;

  -- Conta quanti ticker ha già
  SELECT COUNT(*) INTO v_count
  FROM watchlist
  WHERE user_id = NEW.user_id;

  IF v_count >= FREE_LIMIT THEN
    RAISE EXCEPTION
      'Watchlist limit reached (%). Upgrade to PRO for unlimited watchlist.',
      FREE_LIMIT
      USING ERRCODE = 'P0001';
  END IF;

  RETURN NEW;
END;
$$;


-- 6. TRIGGER: esegui la funzione PRIMA di ogni INSERT su watchlist
DROP TRIGGER IF EXISTS enforce_watchlist_limit ON watchlist;

CREATE TRIGGER enforce_watchlist_limit
  BEFORE INSERT ON watchlist
  FOR EACH ROW
  EXECUTE FUNCTION check_watchlist_limit();
