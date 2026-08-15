"""
Cheruvo — AI Summary con Groq API
Genera un riassunto intelligente delle news di un ticker usando Llama 3.
"""
import os
import json
from groq import Groq
from sentiment_groq import MODELLO_VELOCE

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

PROMPT_TEMPLATE = """Sei un analista finanziario esperto. Ti vengono forniti i titoli delle ultime notizie riguardanti il ticker {ticker} ({company}).

Notizie (dalla più recente alla meno recente):
{headlines}

Sentiment medio calcolato: {avg_sentiment:.2f} (scala da -1 a +1)

Basandoti su queste informazioni, rispondi SOLO con un oggetto JSON valido con questa struttura esatta, senza markdown, senza backtick, senza testo aggiuntivo:
{{
  "giudizio": "bullish" | "bearish" | "neutro",
  "riassunto": "Cinque-sei frasi in italiano che analizzano il contesto di mercato, i fattori che influenzano il sentiment, eventuali rischi o opportunità, e una prospettiva di breve periodo.",
  "temi": ["tema1", "tema2", "tema3"]
}}

Regole:
- giudizio: "bullish" se sentiment > 0.1, "bearish" se < -0.1, "neutro" altrimenti
- riassunto: cinque-sei frasi in italiano, chiaro e diretto
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
            max_tokens=800,
            temperature=0.3,   # bassa per output consistente
        )
        raw = response.choices[0].message.content.strip()
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
    """Fallback rule-based se Groq fallisce o le news sono insufficienti."""
    if avg_sentiment > 0.1:
        giudizio = "bullish"
        riassunto = "Il sentiment delle notizie recenti risulta positivo. Le analisi indicano un orientamento favorevole per questo titolo nel breve periodo. Si consiglia di monitorare eventuali sviluppi nelle prossime sessioni."
    elif avg_sentiment < -0.1:
        giudizio = "bearish"
        riassunto = "Il sentiment delle notizie recenti risulta negativo. Le analisi indicano pressioni ribassiste su questo titolo. Si consiglia cautela e attenzione ai livelli di supporto."
    else:
        giudizio = "neutro"
        riassunto = "Il sentiment delle notizie recenti è bilanciato. Non emergono segnali direzionali forti nel breve periodo. Si consiglia di attendere ulteriori sviluppi prima di prendere decisioni."

    return {
        "giudizio":  giudizio,
        "riassunto": riassunto,
        "temi":      ["Mercato", "Analisi", "Sentiment"],
        "fonte":     "fallback",
    }