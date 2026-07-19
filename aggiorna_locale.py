#!/usr/bin/env python3
"""
aggiorna_locale.py — Aggiorna news e sentiment dal PC, senza GitHub Actions.

Serve quando i minuti Actions del mese sono esauriti: fa esattamente quello
che fa il workflow "Aggiorna news", ma sul tuo computer, quindi gratis.

Uso:
    1) copia .env.example in .env e riempilo con le tue chiavi
       (.env è già ignorato da git: le chiavi non finiscono nel repo)
    2) py -m pip install -r requirements-actions.txt    <- solo la prima volta
    3) py aggiorna_locale.py

Per farlo partire da solo ogni giorno vedi le istruzioni in fondo al file.
"""
import os
import runpy
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
except ImportError:
    print("Manca python-dotenv. Installa le dipendenze con:")
    print("    py -m pip install -r requirements-actions.txt")
    raise SystemExit(1)

# Le chiavi possono stare in backend/.env (quello che usi già per il backend
# in locale) oppure in un .env nella radice. Leggiamo entrambi: il primo che
# definisce una variabile vince, così non devi duplicare niente.
trovati = []
for percorso in (RADICE / ".env", RADICE / "backend" / ".env"):
    if percorso.exists():
        load_dotenv(percorso, override=False)
        trovati.append(percorso.name if percorso.parent == RADICE else f"backend/{percorso.name}")

if not trovati:
    print("Nessun file .env trovato.")
    print("Copia .env.example in .env e riempilo, oppure usa backend/.env.")
    raise SystemExit(1)

# updater.py importa moduli che stanno in backend/ (come fa PYTHONPATH nel workflow)
sys.path.insert(0, str(RADICE / "backend"))

ESSENZIALI = ["DATABASE_URL", "ALPHA_VANTAGE", "GROQ_API_KEY"]
mancanti = [v for v in ESSENZIALI if not os.environ.get(v)]
if mancanti:
    print("Letti:", ", ".join(trovati))
    print("Mancano queste variabili:", ", ".join(mancanti))
    print()
    print("Aggiungile in fondo a backend/.env, una per riga, formato CHIAVE=valore.")
    print("Dove ritrovarle: i secret di GitHub non si possono rileggere, ma i")
    print("valori sono visibili su Render, nella scheda Environment del servizio.")
    print("In alternativa dai siti di origine (Supabase, Alpha Vantage, Groq).")
    raise SystemExit(1)

print("Configurazione letta da:", ", ".join(trovati))

print("Avvio aggiornamento news dal PC...")
print()
runpy.run_path(str(RADICE / "updater.py"), run_name="__main__")


# ─────────────────────────────────────────────────────────────────────────────
# Farlo partire da solo ogni giorno (Windows)
#
#   1. apri "Utilità di pianificazione" (cerca "pianificazione" nel menu Start)
#   2. Crea attività di base  ->  nome: "Cheruvo aggiorna news"
#   3. Attivazione: Ogni giorno, orario a scelta (es. 8:00)
#   4. Azione: Avvia programma
#        Programma:            py
#        Argomenti:            aggiorna_locale.py
#        Inizia da (facoltativo): la cartella cheruvo, percorso completo
#   5. Fine. Se il PC è spento all'orario previsto, l'attività parte
#      al successivo avvio se spunti "Esegui l'attività non appena
#      possibile dopo un avvio pianificato non riuscito" nelle proprietà.
# ─────────────────────────────────────────────────────────────────────────────
