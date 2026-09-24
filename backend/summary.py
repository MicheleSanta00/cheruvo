"""
Cheruvo, riassunto AI con Groq.
Genera un riassunto delle notizie di un ticker con il modello MODELLO_VELOCE
(sentiment_groq.py). Era Llama 3 fino al 16 agosto 2026, quando Groq lo ha
dismesso.
"""
import json
from sentiment_groq import MODELLO_VELOCE, _get_groq


class _ClientPigro:
    """
    Il client Groq, creato alla prima chiamata e non all'import.

    Prima era `client = Groq(api_key=...)` in cima al file: senza la chiave,
    Groq solleva un errore GIA' nel costruttore, e siccome main.py importa
    questo modulo, un GROQ_API_KEY mancante su Render impediva all'INTERO
    backend di partire, notizie e prezzi compresi, per una funzione accessoria.
    Resta un attributo `client` con `.chat.completions.create`, cosi' chi lo
    sostituisce nei test lo trova dove l'ha sempre trovato.
    """
    @property
    def chat(self):
        return _get_groq().chat


client = _ClientPigro()

PROMPT_TEMPLATE = """Sei un analista finanziario esperto. Ti vengono forniti i titoli delle ultime notizie riguardanti il ticker {ticker} ({company}).

Notizie (dalla più recente alla meno recente):
{headlines}

Sentiment medio calcolato: {avg_sentiment:.2f} (scala da -1 a +1)

Basandoti su queste informazioni, rispondi SOLO con un oggetto JSON valido con questa struttura esatta, senza markdown, senza backtick, senza testo aggiuntivo:
{{
  "giudizio": "bullish" | "bearish" | "neutro",
  "riassunto": "Cinque-sei frasi in italiano che riassumono di cosa parlano le notizie, quali fatti pesano sul tono e quali rischi o opportunità vengono citati.",
  "temi": ["tema1", "tema2", "tema3"]
}}

Regole:
- giudizio: "bullish" se sentiment > 0.1, "bearish" se < -0.1, "neutro" altrimenti
- riassunto: cinque-sei frasi in italiano, chiaro e diretto
- descrivi le notizie: niente previsioni sul prezzo, niente consigli di investimento, niente inviti a comprare o vendere
- temi: esattamente 3 temi principali emersi dalle notizie, 1-3 parole ciascuno
"""

def genera_summary(ticker: str, company: str, headlines: list[str], avg_sentiment: float) -> dict:
    """
    Chiama Groq API e restituisce il summary strutturato.
    headlines: lista di titoli news (max 15)
    """
    if not headlines:
        return _fallback(avg_sentiment)

    headlines_str = "\n".join(f"- {h}" for h in headlines[:60])
    prompt = PROMPT_TEMPLATE.format(
        ticker=ticker,
        company=company,
        headlines=headlines_str,
        avg_sentiment=avg_sentiment,
    )

    try:
        response = client.chat.completions.create(
            model=MODELLO_VELOCE,
            messages=[{"role": "user", "content": prompt}],
            # Era 800. Con i GPT-OSS (dal 16 agosto 2026) il ragionamento
            # esce dallo stesso tetto della risposta, e con 800 il JSON
            # poteva arrivare tagliato a meta': json.loads falliva e l'utente
            # riceveva in silenzio il riassunto di ripiego, sempre uguale.
            # Il tetto piu' alto non costa quota (si contano i token usati).
            max_tokens=2500,
            temperature=0.3,   # bassa per output consistente
        )
        raw = (response.choices[0].message.content or "").strip()
        # Alcuni modelli incorniciano il JSON fra backtick: tolti prima di
        # leggerlo, come fa gia' sentiment_groq.score_batch.
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()
        data = json.loads(raw)

        # Validazione campi
        assert data.get("giudizio") in ("bullish", "bearish", "neutro")
        assert isinstance(data.get("riassunto"), str) and len(data["riassunto"]) > 10
        assert isinstance(data.get("temi"), list) and len(data["temi"]) == 3

        return {
            "giudizio":  data["giudizio"],
            "riassunto": data["riassunto"],
            "temi":      data["temi"][:3],
            "fonte":     f"groq/{MODELLO_VELOCE}",
        }

    except (json.JSONDecodeError, AssertionError, KeyError):
        # Se il JSON non è valido fallback basato sul sentiment numerico
        return _fallback(avg_sentiment)

    except Exception as e:
        raise RuntimeError(f"Groq API error: {e}")


def _fallback(avg_sentiment: float) -> dict:
    """
    Ripiego a regole se Groq fallisce o le notizie non bastano.

    Le frasi DESCRIVONO le notizie e non danno indicazioni (24 settembre 2026).

    Prima dicevano "Si consiglia cautela e attenzione ai livelli di supporto"
    e "Si consiglia di attendere ulteriori sviluppi prima di prendere
    decisioni": frasi da consulente, scritte da un programma che non sa nulla
    del prezzo, su un prodotto che dichiara ovunque di non dare consigli. E
    parlavano di "pressioni ribassiste" e di "orientamento favorevole per
    questo titolo", cioe' del prezzo, quando il numero da cui nascono e' solo
    il tono medio dei titoli di giornale. Qui si dice quello che si sa.
    """
    if avg_sentiment > 0.1:
        giudizio = "bullish"
        riassunto = ("Il tono medio delle notizie recenti su questo titolo e' positivo. "
                     "E' una misura di come ne parla la stampa, non una previsione sul prezzo. "
                     "Il riassunto dettagliato non e' disponibile in questo momento.")
    elif avg_sentiment < -0.1:
        giudizio = "bearish"
        riassunto = ("Il tono medio delle notizie recenti su questo titolo e' negativo. "
                     "E' una misura di come ne parla la stampa, non una previsione sul prezzo. "
                     "Il riassunto dettagliato non e' disponibile in questo momento.")
    else:
        giudizio = "neutro"
        riassunto = ("Il tono medio delle notizie recenti su questo titolo e' vicino allo zero. "
                     "E' una misura di come ne parla la stampa, non una previsione sul prezzo. "
                     "Il riassunto dettagliato non e' disponibile in questo momento.")

    return {
        "giudizio":  giudizio,
        "riassunto": riassunto,
        "temi":      ["Mercato", "Analisi", "Sentiment"],
        "fonte":     "fallback",
    }
