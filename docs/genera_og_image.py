"""
Genera l'immagine di anteprima (Open Graph) di Cheruvo dai dati VERI.

Sostituisce docs/og-image.png, che era un mockup del 14 luglio 2026 con
numeri inventati e, cosa peggiore, con "Reuters" e "Bloomberg" indicati come
fonti: due testate che Cheruvo non ha mai avuto in licenza e che il 7 agosto
sono state cancellate dall'archivio proprio per quel motivo.

Qui dentro ogni numero e' quello che il sito mostra adesso, e la fonte
dichiarata e' GDELT, che e' l'unica.
"""
import os

from PIL import Image, ImageDraw, ImageFont

QUI = os.path.dirname(os.path.abspath(__file__))

L = 1200
A = 630

SFONDO   = (10, 13, 20)
PANNELLO = (17, 22, 33)
BORDO    = (32, 40, 56)
TESTO    = (233, 237, 243)
FIOCO    = (122, 134, 154)
VERDE    = (52, 211, 153)
ROSSO    = (248, 113, 113)
AZZURRO  = (96, 165, 250)

F = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

def f(p, b=False, mono=False):
    return ImageFont.truetype(FM if mono else (FB if b else F), p)

img = Image.new("RGB", (L, A), SFONDO)
d = ImageDraw.Draw(img)

def pannello(x, y, w, h, r=14, sfondo=PANNELLO):
    d.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=sfondo, outline=BORDO, width=1)

# ── intestazione ─────────────────────────────────────────────────────────
#
# Il marchio vero, non un cerchio disegnato a mano.
#
# Si usa `logo-v2.png`, che sono le due lune bianche su trasparente, e non
# `favicon.png`, che le ha dentro un cerchio NERO: su questo fondo scuro quel
# cerchio diventerebbe un buco. Su sfondo scuro un marchio si mette in bianco
# e senza pastiglia, che e' anche come lo mostra l'app.
LATO_LOGO = 46
try:
    logo = Image.open(os.path.join(QUI, "logo-v2.png")).convert("RGBA")
    logo = logo.resize((LATO_LOGO, LATO_LOGO), Image.LANCZOS)
    img.paste(logo, (56, 44), logo)      # il terzo argomento e' la maschera
    x_testo = 56 + LATO_LOGO + 18
except FileNotFoundError:
    x_testo = 56                          # senza file si scrive solo il nome

d.text((x_testo, 48), "Cheruvo", font=f(28, True), fill=TESTO)
d.text((x_testo, 82), "cheruvo.com", font=f(15), fill=FIOCO)

d.text((L - 56, 52), "Il sentiment delle criptovalute,", font=f(17), fill=FIOCO, anchor="ra")
d.text((L - 56, 78), "letto dalle notizie", font=f(17), fill=FIOCO, anchor="ra")

# ── quattro numeri veri ──────────────────────────────────────────────────
METRICHE = [("NOTIZIE OGGI", "412"), ("IN ARCHIVIO", "4.446"),
            ("MONETE E TITOLI", "44"), ("AGGIORNATO", "ogni ora")]
x = 56
larg = (L - 112 - 3 * 16) // 4
for et, val in METRICHE:
    pannello(x, 124, larg, 92)
    d.text((x + 20, 144), et, font=f(12, True), fill=FIOCO)
    d.text((x + 20, 168), val, font=f(30, True), fill=TESTO)
    x += larg + 16

# ── la classifica, coi numeri di adesso ──────────────────────────────────
RIGHE = [("BTC", "Bitcoin", 194, -0.14), ("XRP", "XRP", 66, -0.18),
         ("ETH", "Ethereum", 35, -0.02), ("SOL", "Solana", 9, +0.11),
         ("DOGE", "Dogecoin", 9, +0.06), ("OP", "Optimism", 8, +0.31)]

pannello(56, 240, L - 112, 268)
d.text((80, 262), "MERCATO OGGI", font=f(13, True), fill=FIOCO)
d.text((80, 284), "Sentiment delle ultime 48 ore", font=f(15), fill=TESTO)
d.text((L - 80, 266), "GDELT", font=f(13, True), fill=AZZURRO, anchor="ra")

y = 322
for sig, nome, news, s in RIGHE:
    col = VERDE if s > 0.08 else (ROSSO if s < -0.08 else FIOCO)
    d.text((80, y), sig, font=f(19, True), fill=TESTO)
    d.text((80 + 72, y + 4), nome, font=f(15), fill=FIOCO)
    # barra proporzionale al numero di notizie
    largh = int(max(0.08, (min(news, 200) / 200) ** 0.5) * 300)
    d.rounded_rectangle([560, y + 8, 560 + largh, y + 18], radius=5, fill=BORDO)
    d.text((880, y + 3), f"{news} notizie", font=f(14), fill=FIOCO)
    d.text((L - 80, y), f"{s:+.2f}", font=f(19, True, mono=True), fill=col, anchor="ra")
    y += 30

# ── la riga che nessun concorrente scrive ────────────────────────────────
d.text((56, 540), "Non prevede il prezzo, e non lo promette.",
       font=f(17, True), fill=TESTO)
d.text((56, 568), "Gratis, senza pubblicit\u00e0, senza account per guardare.",
       font=f(16), fill=FIOCO)

img.save(os.path.join(QUI, "og-image.png"), optimize=True)
print("creata docs/og-image.png", img.size)
print("\nI numeri qui dentro sono scritti a mano: vanno riletti da")
print("/api/market/today e /api/market/stats prima di rigenerare,")
print("altrimenti l'immagine ricomincia a raccontare cose vecchie.")
