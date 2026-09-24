-- 009_watchlist_senza_muro.sql
-- Da eseguire UNA volta nel SQL Editor di Supabase. Scritta il 24 settembre 2026.
--
-- IL DIFETTO
--
-- La migrazione 002 ha messo un trigger su `watchlist` che rifiuta il quarto
-- titolo a chi non ha una riga 'pro' in `subscriptions`. Dal 6 agosto 2026 il
-- paywall e' spento e gli abbonati sono zero, quindi quel "chi" e' TUTTI.
--
-- Il frontend non se ne accorgeva, per due motivi che si sommano:
--
--   1. `isPro` parte da true, quindi l'interfaccia permette di aggiungere
--      quanti titoli si vuole;
--   2. supabase-js NON solleva eccezioni: restituisce { error }, e
--      Sidebar.jsx non lo guardava. Il titolo compariva in lista, il database
--      l'aveva rifiutato, e al ricaricamento della pagina spariva.
--
-- E il primo accesso riempie la watchlist con TRE titoli da solo
-- (PRECARICATI in Sidebar.jsx): un utente nuovo era gia' al limite prima di
-- toccare niente. Ogni titolo che aggiungeva di suo veniva perso in silenzio.
-- Anche prima del 6 agosto il conto non tornava: il frontend diceva 5, il
-- database 3.
--
-- LA CORREZIONE
--
-- Il trigger resta, perche' serve ancora a una cosa: la chiave pubblica di
-- Supabase sta nel JavaScript servito a chiunque, e la RLS permette a ogni
-- utente di inserire righe proprie SENZA limite. Senza tetto, uno script
-- potrebbe riempire la tabella di milioni di righe. Il tetto diventa quindi
-- una protezione (100 titoli, che nessuna persona segue) e non piu' un
-- piano commerciale.
--
-- Quando il paywall si riaccende, FREE_LIMIT va rimesso uguale a
-- MAX_WATCHLIST_FREE in frontend/src/components/Sidebar.jsx (oggi 5), e le
-- due cifre vanno cambiate INSIEME.

CREATE OR REPLACE FUNCTION check_watchlist_limit()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
-- Senza search_path fisso una funzione SECURITY DEFINER puo' essere dirottata
-- da un oggetto con lo stesso nome in un altro schema: e' l'avviso
-- "function_search_path_mutable" della console di Supabase.
SET search_path = public
AS $$
DECLARE
  v_status   TEXT;
  v_count    INT;
  TETTO      CONSTANT INT := 100;   -- per tutti, abbonati compresi
  FREE_LIMIT CONSTANT INT := 100;   -- col paywall acceso: 5, come Sidebar.jsx
BEGIN
  SELECT COUNT(*) INTO v_count
  FROM watchlist
  WHERE user_id = NEW.user_id;

  IF v_count >= TETTO THEN
    RAISE EXCEPTION 'Watchlist piena (% titoli).', TETTO
      USING ERRCODE = 'P0001';
  END IF;

  SELECT status INTO v_status
  FROM subscriptions
  WHERE user_id = NEW.user_id;

  IF v_status = 'pro' THEN
    RETURN NEW;
  END IF;

  IF v_count >= FREE_LIMIT THEN
    RAISE EXCEPTION 'Watchlist limit reached (%). Upgrade to PRO for unlimited watchlist.',
      FREE_LIMIT
      USING ERRCODE = 'P0001';
  END IF;

  RETURN NEW;
END;
$$;

-- Il trigger punta gia' a questa funzione (migrazione 002): ricrearlo non
-- serve, ma se per qualche motivo mancasse lo si rimette uguale.
DROP TRIGGER IF EXISTS enforce_watchlist_limit ON watchlist;
CREATE TRIGGER enforce_watchlist_limit
  BEFORE INSERT ON watchlist
  FOR EACH ROW
  EXECUTE FUNCTION check_watchlist_limit();


-- LA FORMA DEL SIMBOLO
--
-- La stessa regola del backend (backend/richieste.py). Con la chiave
-- pubblica si poteva scrivere in watchlist qualunque stringa, e quelle
-- stringhe finivano nel cron (updater.py le raccoglie come titoli da
-- seguire) e nelle email.
--
-- NOT VALID: controlla solo le righe nuove. Se in tabella ce ne fosse gia'
-- una strana la migrazione non fallisce; la si trova con la query in fondo.
ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS watchlist_ticker_forma;
ALTER TABLE watchlist ADD CONSTRAINT watchlist_ticker_forma
  CHECK (ticker ~ '^[A-Z0-9^][A-Z0-9.=^-]{0,19}$') NOT VALID;


-- ── Come si verifica ──────────────────────────────────────────────────────
--
--   -- deve dire 100 e 100
--   select prosrc from pg_proc where proname = 'check_watchlist_limit';
--
--   -- righe gia' presenti che non rispettano la forma (di solito nessuna)
--   select user_id, ticker from watchlist
--   where ticker !~ '^[A-Z0-9^][A-Z0-9.=^-]{0,19}$';
--
-- Poi, dall'app: aggiungere un quarto titolo alla watchlist, ricaricare la
-- pagina e controllare che sia ancora li'. E' esattamente il gesto che prima
-- falliva in silenzio.
