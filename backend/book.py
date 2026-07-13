"""
book.py — "Lezioni dal Libro": il docente carica il SUO materiale (PDF o foto
delle pagine), l'AI ne ricava una mappa dei concetti e genera bozze di lezione
nei 4 motori esistenti (quiz, flashcard, scenario, simulatore).

Principi (vedi Cheruvo_Lezioni_dal_Libro_Piano.md):
- Il file resta privato: vive in una cartella temporanea SOLO per la durata
  del job e viene eliminato a fine generazione (cleanup anche all'avvio).
- Nel DB si salva solo materiale DERIVATO (mappa dei concetti riformulata),
  mai il testo del libro.
- Le lezioni generate nascono come bozze (status='draft', visibility='class'):
  niente arriva agli studenti senza revisione e pubblicazione del docente.
- Riservato ai docenti (academy_profiles.role = 'teacher') e agli admin.
"""

import os
import io
import json
import re
import time
import base64
import shutil
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from typing import Literal, Optional

from database import get_pool
from auth import get_current_user
from academy import _validate_content, _is_admin, _j

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/academy/book")

# ── Configurazione ──────────────────────────────────────────────────────────
BOOK_TMP = Path(os.environ.get("BOOK_TMP_DIR", "/tmp/cheruvo_books"))
MAX_UPLOAD_BYTES = 25 * 1024 * 1024      # 25 MB totali per upload
MAX_PDF_PAGES = 400                       # oltre: chiedere di caricare un capitolo
MAX_IMAGES = 20                           # foto per upload
MAX_OCR_PAGES = 30                        # pagine OCR (vision) per job
MAX_CHAPTER_CHARS = 24_000                # testo capitolo passato all'LLM (≈6k token)
TMP_MAX_AGE_SEC = 24 * 3600               # cleanup file temporanei più vecchi di 24h

GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

PDF_EXT = {".pdf"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}

LEVELS = ["base", "intermedio", "avanzato"]


# ── Helpers DB (stesso pattern di academy.py) ───────────────────────────────
def _conn():
    return get_pool().getconn()

def _rel(conn):
    get_pool().putconn(conn)


def init_book_tables():
    """Crea le tabelle se non esistono (idempotente) e pulisce i temporanei."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS book_jobs (
                id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id    UUID NOT NULL,
                status     TEXT NOT NULL DEFAULT 'extracting',
                progress   INT DEFAULT 0,
                step       TEXT,
                toc        JSONB,
                params     JSONB,
                result     JSONB,
                error      TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS book_maps (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id       UUID NOT NULL,
                job_id        UUID,
                book_title    TEXT,
                chapter_title TEXT,
                concepts      JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_bjobs_user ON book_jobs (user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_bmaps_user ON book_maps (user_id, created_at);
        """)
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    _cleanup_tmp()


def _cleanup_tmp():
    """Elimina le cartelle temporanee dei job più vecchie di 24h (privacy by design)."""
    try:
        BOOK_TMP.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for d in BOOK_TMP.iterdir():
            try:
                if d.is_dir() and now - d.stat().st_mtime > TMP_MAX_AGE_SEC:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass
    except OSError as e:
        logger.warning("cleanup tmp libri: %s", e)


def _job_dir(job_id: str) -> Path:
    return BOOK_TMP / str(job_id)


def _purge_job_files(job_id: str):
    """Il libro si elabora e si scarta: mai archiviato."""
    shutil.rmtree(_job_dir(job_id), ignore_errors=True)


# ── Autorizzazione docente ──────────────────────────────────────────────────
def _is_teacher(user_id: str) -> bool:
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role FROM academy_profiles WHERE user_id = %s", (user_id,))
        r = cur.fetchone()
        cur.close()
    finally:
        _rel(conn)
    return bool(r and r[0] == "teacher")


async def require_teacher(user: dict = Depends(get_current_user)) -> dict:
    if not (_is_teacher(user["sub"]) or _is_admin(user["sub"])):
        raise HTTPException(status_code=403, detail="Funzione riservata ai docenti (imposta il ruolo Docente nelle impostazioni Academy)")
    return user


# ── Stato job ───────────────────────────────────────────────────────────────
def _upd(job_id: str, **fields):
    if not fields:
        return
    sets, vals = [], []
    for k, v in fields.items():
        if k in ("toc", "params", "result"):
            sets.append(f"{k} = %s::jsonb")
            vals.append(json.dumps(v))
        else:
            sets.append(f"{k} = %s")
            vals.append(v)
    vals.append(job_id)
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE book_jobs SET {', '.join(sets)} WHERE id = %s", vals)
        conn.commit()
        cur.close()
    finally:
        _rel(conn)


def _get_job(job_id: str):
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT id, user_id, status, progress, step, toc, params, result, error
                       FROM book_jobs WHERE id = %s""", (job_id,))
        r = cur.fetchone()
        cur.close()
    finally:
        _rel(conn)
    if not r:
        return None
    return {"id": str(r[0]), "user_id": str(r[1]), "status": r[2], "progress": r[3] or 0,
            "step": r[4], "toc": _j(r[5]) or [], "params": _j(r[6]), "result": _j(r[7]), "error": r[8]}


# ── Groq helper (con retry sui rate limit del free tier) ────────────────────
def _groq_json(messages, model=None, max_tokens=3000, temperature=0.4, retries=2):
    from groq import Groq
    client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
    last = None
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model or GROQ_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:  # rate limit / json rotto: riprova
            last = e
            msg = str(e).lower()
            if attempt < retries and ("rate" in msg or "429" in msg or "json" in msg or "expecting" in msg):
                time.sleep(12 * (attempt + 1))
                continue
            raise
    raise last


def _groq_text(messages, model=None, max_tokens=2000, temperature=0.1):
    from groq import Groq
    client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
    resp = client.chat.completions.create(
        model=model or GROQ_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


# ── Estrazione: PDF ─────────────────────────────────────────────────────────
_CHAP_RE = re.compile(
    r"^\s*(capitolo|chapter|unit[àa]|modulo|parte|sezione|lezione)\s+([0-9]+|[IVXLC]+)\b[\s.:–—-]*(.{0,80})",
    re.IGNORECASE,
)


def _detect_chapters_from_text(pages: list[str]) -> list[dict]:
    """Fallback senza indice PDF: cerca intestazioni tipo 'Capitolo 3 — Titolo'
    nelle prime righe di ogni pagina. Ritorna [] se trova meno di 2 capitoli."""
    found = []
    for i, txt in enumerate(pages):
        for line in (txt or "").splitlines()[:6]:
            m = _CHAP_RE.match(line.strip())
            if m:
                title = (m.group(3) or "").strip(" .:-–—")
                label = f"{m.group(1).capitalize()} {m.group(2)}"
                found.append({"title": f"{label}{' — ' + title if title else ''}", "start": i})
                break
    # dedup: la stessa intestazione ripetuta pagina dopo pagina (colontitoli)
    chapters = []
    for c in found:
        if chapters and c["title"].strip().lower() == chapters[-1]["title"].strip().lower():
            continue
        chapters.append(c)
    if len(chapters) < 2:
        return []
    for k, c in enumerate(chapters):
        c["end"] = (chapters[k + 1]["start"] - 1) if k + 1 < len(chapters) else len(pages) - 1
        c["idx"] = k
    return chapters


def _extract_pdf(job_id: str, pdf_path: Path) -> tuple[list[str], list[dict], str]:
    """Ritorna (pagine_testo, capitoli, titolo_libro). OCR vision per le scansioni."""
    import fitz  # PyMuPDF — import pigro: serve solo qui

    doc = fitz.open(pdf_path)
    try:
        if doc.page_count > MAX_PDF_PAGES:
            raise ValueError(f"PDF troppo lungo ({doc.page_count} pagine). Carica un capitolo alla volta (max {MAX_PDF_PAGES} pagine).")

        book_title = (doc.metadata or {}).get("title") or pdf_path.stem.replace("_", " ")
        pages = []
        for i, page in enumerate(doc):
            pages.append(page.get_text("text") or "")
            if i % 25 == 0:
                _upd(job_id, progress=min(40, 5 + int(35 * i / max(1, doc.page_count))))

        # PDF scansionato (niente layer di testo) → OCR con modello vision
        if sum(len(p.strip()) for p in pages) < 200:
            if doc.page_count > MAX_OCR_PAGES:
                raise ValueError(f"Questo PDF è una scansione senza testo: posso leggerne al massimo {MAX_OCR_PAGES} pagine per volta. Carica un capitolo.")
            _upd(job_id, step="Il PDF è una scansione: leggo le pagine con l'AI…", progress=15)
            pages = []
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=120)
                pages.append(_ocr_image_bytes(pix.tobytes("png")))
                _upd(job_id, progress=min(60, 15 + int(45 * (i + 1) / doc.page_count)),
                     step=f"Leggo la pagina {i + 1} di {doc.page_count}…")

        # Capitoli: 1) indice del PDF  2) euristica sul testo  3) documento intero
        toc_raw = doc.get_toc(simple=True) or []
        lvl1 = [t for t in toc_raw if t[0] == 1]
        if len(lvl1) < 2:
            lvl1 = [t for t in toc_raw if t[0] <= 2]
        chapters = []
        if len(lvl1) >= 2:
            for k, (_lvl, title, pg) in enumerate(lvl1):
                start = max(0, (pg or 1) - 1)
                end = (max(0, (lvl1[k + 1][2] or 1) - 2)) if k + 1 < len(lvl1) else doc.page_count - 1
                chapters.append({"idx": k, "title": (title or f"Capitolo {k + 1}").strip()[:120],
                                 "start": start, "end": max(start, end)})
        if not chapters:
            chapters = _detect_chapters_from_text(pages)
        if not chapters:
            chapters = [{"idx": 0, "title": "Documento completo", "start": 0, "end": len(pages) - 1}]
        return pages, chapters, book_title
    finally:
        doc.close()


# ── Estrazione: foto (OCR vision) ───────────────────────────────────────────
def _ocr_image_bytes(png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode()
    txt = _groq_text(
        [{"role": "user", "content": [
            {"type": "text", "text": "Trascrivi fedelmente TUTTO il testo di questa pagina di libro, nell'ordine di lettura. Solo il testo, senza commenti."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}],
        model=GROQ_VISION_MODEL, max_tokens=2500, temperature=0.0,
    )
    return txt.strip()


def _extract_images(job_id: str, img_paths: list[Path]) -> tuple[list[str], list[dict], str]:
    pages = []
    for i, p in enumerate(sorted(img_paths)):
        _upd(job_id, step=f"Leggo la foto {i + 1} di {len(img_paths)}…",
             progress=min(60, 10 + int(50 * i / len(img_paths))))
        pages.append(_ocr_image_bytes(p.read_bytes()))
    chapters = _detect_chapters_from_text(pages) or [
        {"idx": 0, "title": "Pagine fotografate", "start": 0, "end": len(pages) - 1}]
    return pages, chapters, "Pagine fotografate"


# ── Task in background: estrazione ──────────────────────────────────────────
def _extract_job(job_id: str):
    try:
        d = _job_dir(job_id)
        pdfs = list(d.glob("*.pdf"))
        imgs = [p for p in d.iterdir() if p.suffix.lower() in IMG_EXT]
        _upd(job_id, status="extracting", step="Estraggo il testo…", progress=5)

        if pdfs:
            pages, chapters, title = _extract_pdf(job_id, pdfs[0])
        else:
            pages, chapters, title = _extract_images(job_id, imgs)

        # il testo resta SOLO su disco temporaneo, mai nel DB
        (d / "pages.json").write_text(json.dumps({"title": title, "pages": pages}), encoding="utf-8")
        toc = [{"idx": c["idx"], "title": c["title"], "start": c["start"] + 1, "end": c["end"] + 1}
               for c in chapters]
        _upd(job_id, status="ready", step="Indice pronto", progress=100, toc=toc)
    except Exception as e:
        logger.error("book extract %s: %s", job_id, e)
        _purge_job_files(job_id)
        _upd(job_id, status="error", error=str(e)[:300])


# ── Mappa dei concetti + generazione lezioni ────────────────────────────────
_MAP_SYSTEM = (
    "Sei un assistente didattico. Dal testo di un capitolo di libro scolastico produci una "
    "MAPPA DEI CONCETTI in JSON, RIFORMULANDO tutto con parole tue: non copiare frasi del libro. "
    "Tutti i testi sono bilingui {\"it\":\"...\",\"en\":\"...\"}. Schema: "
    '{"summary":{"it":"","en":""},"concepts":[{"name":{"it":"","en":""},"explain":{"it":"","en":""},'
    '"example":{"it":"","en":""}}],"terms":[{"term":{"it":"","en":""},"def":{"it":"","en":""}}]} '
    "Estrai 5-12 concetti e 8-16 termini. Rispondi SOLO con JSON valido."
)

_DIFF_HINT = {
    "base": "Difficoltà BASE: domande di comprensione e memoria, distrattori chiaramente sbagliati, linguaggio semplicissimo.",
    "intermedio": "Difficoltà INTERMEDIA: domande di comprensione e prima applicazione, distrattori plausibili.",
    "avanzato": "Difficoltà AVANZATA: domande applicative e di ragionamento, distrattori molto vicini alla risposta corretta, casi concreti.",
}

_GEN_SCHEMAS = {
    "quiz": '{"title":{"it":"","en":""},"content":{"timer_sec":30,"pass_score":70,"questions":[{"q":{"it":"","en":""},"options":[{"it":"","en":""},{"it":"","en":""},{"it":"","en":""},{"it":"","en":""}],"correct":0,"explain":{"it":"","en":""}}]}}',
    "flashcard": '{"title":{"it":"","en":""},"content":{"deck":[{"term":{"it":"","en":""},"definition":{"it":"","en":""},"example":{"it":"","en":""}}]}}',
    "scenario": '{"title":{"it":"","en":""},"content":{"start":"n1","nodes":{"n1":{"text":{"it":"","en":""},"choices":[{"label":{"it":"","en":""},"feedback":{"it":"","en":""},"goto":"n2 o stringa vuota per finire"}]}}}}',
    "simulator": '{"title":{"it":"","en":""},"content":{"model":"uno tra: compound_interest, pac, inflation, budget_50_30_20","teach":{"it":"","en":""}}}',
}
_GEN_ASK = {
    "quiz": "Crea un quiz di 5-6 domande (4 opzioni) sui concetti della mappa.",
    "flashcard": "Crea un mazzo di 8-12 flashcard (termine, definizione, esempio) dai termini e concetti della mappa.",
    "scenario": "Crea una storia a bivi (3-4 scene, nodi n1/n2/…) che fa APPLICARE i concetti della mappa a una situazione concreta.",
    "simulator": "Scegli il modello di simulatore più attinente ai concetti della mappa e scrivi una spiegazione 'in parole povere' che li collega ai cursori del simulatore.",
}


def _gen_lesson(ltype: str, level: str, chapter_title: str, concept_map: dict, note: str = "") -> tuple[dict, dict]:
    """Genera (title, content) per un tipo/livello dai concetti. Valida col Pydantic esistente."""
    system = (
        "Sei un autore di lezioni interattive per studenti. Lavori SOLO dai concetti forniti "
        "(mai citare o copiare testo di libri; riformula sempre, esercizi originali). "
        "Tutti i testi bilingui {\"it\":\"...\",\"en\":\"...\"}. Linguaggio chiaro, niente consulenza finanziaria. "
        + _DIFF_HINT.get(level, _DIFF_HINT["intermedio"])
        + " Rispondi SOLO con JSON valido. Schema: " + _GEN_SCHEMAS[ltype]
    )
    prompt = (
        f"Capitolo: {chapter_title}\nMappa dei concetti (JSON):\n{json.dumps(concept_map, ensure_ascii=False)[:12000]}\n\n"
        + _GEN_ASK[ltype]
        + (f"\nIndicazione del docente: {note}" if note else "")
    )
    data = _groq_json(
        [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        max_tokens=3000, temperature=0.5,
    )
    title = data.get("title") or {"it": chapter_title, "en": chapter_title}
    content = _validate_content(ltype, data.get("content") or {})
    return title, content


def _insert_lesson(user_id: str, ltype: str, level: str, title: dict, content: dict) -> str:
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO academy_lessons (path_id, type, title, content, sort_order, status, level, created_by, visibility)
            VALUES (NULL, %s, %s::jsonb, %s::jsonb, 0, 'draft', %s, %s, 'class')
            RETURNING id
        """, (ltype, json.dumps(title), json.dumps(content), level, user_id))
        lid = str(cur.fetchone()[0])
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return lid


def _generate_job(job_id: str, user_id: str):
    try:
        job = _get_job(job_id)
        params = job["params"] or {}
        titles = params.get("titles") or {}
        chapters = [dict(c, title=(titles.get(str(c["idx"])) or c["title"]).strip()[:120])
                    for c in job["toc"] if c["idx"] in set(params["chapters"])]
        per_ch = params["lessons_per_chapter"]
        types = params["types"]
        difficulty = params["difficulty"]

        d = _job_dir(job_id)
        data = json.loads((d / "pages.json").read_text(encoding="utf-8"))
        pages, book_title = data["pages"], data.get("title") or "Libro"

        total = max(1, len(chapters) * (1 + per_ch))
        done = 0
        result = {"lessons": [], "maps": []}

        for c in chapters:
            # 1) mappa dei concetti (l'unica cosa derivata che salviamo)
            _upd(job_id, step=f"Individuo i concetti di «{c['title']}»…",
                 progress=int(100 * done / total))
            text = "\n".join(pages[c["start"] - 1: c["end"]])[:MAX_CHAPTER_CHARS]
            cmap = _groq_json(
                [{"role": "system", "content": _MAP_SYSTEM},
                 {"role": "user", "content": f"Capitolo: {c['title']}\n\nTesto:\n{text}"}],
                max_tokens=3500, temperature=0.3,
            )
            if not cmap.get("concepts"):
                raise ValueError(f"Non sono riuscito a estrarre concetti da «{c['title']}»")
            conn = _conn()
            try:
                cur = conn.cursor()
                cur.execute("""INSERT INTO book_maps (user_id, job_id, book_title, chapter_title, concepts)
                               VALUES (%s, %s, %s, %s, %s::jsonb) RETURNING id""",
                            (user_id, job_id, book_title[:200], c["title"][:200], json.dumps(cmap)))
                map_id = str(cur.fetchone()[0])
                conn.commit()
                cur.close()
            finally:
                _rel(conn)
            result["maps"].append({"id": map_id, "chapter": c["title"]})
            done += 1

            # 2) lezioni: cicla i tipi scelti; difficoltà 'mista' cicla i livelli
            for i in range(per_ch):
                ltype = types[i % len(types)]
                level = LEVELS[i % len(LEVELS)] if difficulty == "mista" else difficulty
                _upd(job_id, step=f"Creo {ltype} ({level}) per «{c['title']}»…",
                     progress=int(100 * done / total))
                title, content = _gen_lesson(ltype, level, c["title"], cmap)
                lid = _insert_lesson(user_id, ltype, level, title, content)
                result["lessons"].append({"id": lid, "type": ltype, "level": level,
                                          "title": title, "map_id": map_id, "chapter": c["title"]})
                done += 1
                _upd(job_id, result=result)

        _upd(job_id, status="done", step="Bozze pronte", progress=100, result=result)
    except Exception as e:
        logger.error("book generate %s: %s", job_id, e)
        _upd(job_id, status="error", error=str(e)[:300])
    finally:
        _purge_job_files(job_id)   # il libro si elabora e si scarta, sempre


# ── Modelli richieste ───────────────────────────────────────────────────────
class GenerateIn(BaseModel):
    job_id: str
    chapters: list[int]
    lessons_per_chapter: int = 4
    difficulty: Literal["base", "intermedio", "avanzato", "mista"] = "intermedio"
    types: list[Literal["quiz", "flashcard", "scenario", "simulator"]] = ["quiz", "flashcard", "scenario", "simulator"]
    titles: Optional[dict[str, str]] = None   # titoli capitolo corretti dal docente {idx: titolo}

class RegenerateIn(BaseModel):
    lesson_id: str
    map_id: str
    note: str = ""

class PublishIn(BaseModel):
    lesson_ids: list[str]
    class_id: str
    due: Optional[str] = None     # testo libero, es. "20 luglio"
    note: Optional[str] = None


# ── Endpoint ────────────────────────────────────────────────────────────────
@router.post("/upload")
async def upload_book(background_tasks: BackgroundTasks,
                      files: list[UploadFile] = File(...),
                      user: dict = Depends(require_teacher)):
    """1 PDF oppure 1-20 foto delle pagine (max 25 MB totali)."""
    if not files:
        raise HTTPException(status_code=400, detail="Nessun file")
    exts = [Path(f.filename or "").suffix.lower() for f in files]
    is_pdf = exts[0] in PDF_EXT
    if is_pdf and len(files) > 1:
        raise HTTPException(status_code=400, detail="Carica un solo PDF alla volta")
    if not is_pdf:
        if any(e not in IMG_EXT for e in exts):
            raise HTTPException(status_code=415, detail="Formati accettati: PDF oppure foto JPG/PNG/WebP")
        if len(files) > MAX_IMAGES:
            raise HTTPException(status_code=400, detail=f"Massimo {MAX_IMAGES} foto per volta")

    blobs, total = [], 0
    for f in files:
        b = await f.read()
        total += len(b)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File troppo grande (max 25 MB). Carica un capitolo alla volta.")
        blobs.append((Path(f.filename or "file").name, b))

    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO book_jobs (user_id, status, step) VALUES (%s, 'extracting', 'In coda…') RETURNING id",
                    (user["sub"],))
        job_id = str(cur.fetchone()[0])
        conn.commit()
        cur.close()
    finally:
        _rel(conn)

    d = _job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    if is_pdf:
        (d / "book.pdf").write_bytes(blobs[0][1])
    else:
        for i, (_name, b) in enumerate(blobs):
            (d / f"page_{i:03d}{exts[i]}").write_bytes(b)

    background_tasks.add_task(_extract_job, job_id)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, user: dict = Depends(require_teacher)):
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")
    if job["user_id"] != user["sub"] and not _is_admin(user["sub"]):
        raise HTTPException(status_code=403, detail="Non è un tuo job")
    return {k: job[k] for k in ("id", "status", "progress", "step", "toc", "result", "error")}


@router.post("/generate")
def generate(body: GenerateIn, background_tasks: BackgroundTasks,
             user: dict = Depends(require_teacher)):
    job = _get_job(body.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")
    if job["user_id"] != user["sub"] and not _is_admin(user["sub"]):
        raise HTTPException(status_code=403, detail="Non è un tuo job")
    if job["status"] != "ready":
        raise HTTPException(status_code=409, detail="L'estrazione non è ancora pronta")
    if not body.chapters:
        raise HTTPException(status_code=400, detail="Scegli almeno un capitolo")
    if not body.types:
        raise HTTPException(status_code=400, detail="Scegli almeno un tipo di lezione")
    valid_idx = {c["idx"] for c in job["toc"]}
    if any(i not in valid_idx for i in body.chapters):
        raise HTTPException(status_code=400, detail="Capitolo non valido")
    n = max(1, min(10, body.lessons_per_chapter))

    _upd(body.job_id, status="generating", progress=0, step="Preparo la generazione…",
         params={"chapters": body.chapters, "lessons_per_chapter": n,
                 "difficulty": body.difficulty, "types": body.types,
                 "titles": body.titles or {}})
    background_tasks.add_task(_generate_job, body.job_id, job["user_id"])
    return {"status": "generating", "job_id": body.job_id}


@router.post("/regenerate")
def regenerate(body: RegenerateIn, user: dict = Depends(require_teacher)):
    """Rigenera una singola bozza dalla sua mappa dei concetti, con nota del docente."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT type, level, created_by FROM academy_lessons WHERE id = %s", (body.lesson_id,))
        lrow = cur.fetchone()
        cur.execute("SELECT chapter_title, concepts, user_id FROM book_maps WHERE id = %s", (body.map_id,))
        mrow = cur.fetchone()
        cur.close()
    finally:
        _rel(conn)
    if not lrow or not mrow:
        raise HTTPException(status_code=404, detail="Lezione o mappa non trovata")
    if str(lrow[2]) != user["sub"] and not _is_admin(user["sub"]):
        raise HTTPException(status_code=403, detail="Puoi rigenerare solo le tue lezioni")
    if str(mrow[2]) != user["sub"] and not _is_admin(user["sub"]):
        raise HTTPException(status_code=403, detail="Mappa non tua")

    try:
        title, content = _gen_lesson(lrow[0], lrow[1] or "intermedio", mrow[0] or "", _j(mrow[1]), note=body.note[:300])
    except HTTPException:
        raise
    except Exception as e:
        logger.error("book regenerate: %s", e)
        raise HTTPException(status_code=503, detail="Rigenerazione non riuscita, riprova")

    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""UPDATE academy_lessons SET title = %s::jsonb, content = %s::jsonb, updated_at = NOW()
                       WHERE id = %s""", (json.dumps(title), json.dumps(content), body.lesson_id))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"id": body.lesson_id, "title": title, "content": content}


@router.post("/publish")
def publish(body: PublishIn, user: dict = Depends(require_teacher)):
    """Pubblica le bozze scelte e le assegna alla classe (post in bacheca)."""
    if not body.lesson_ids:
        raise HTTPException(status_code=400, detail="Nessuna lezione selezionata")
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role FROM class_members WHERE class_id = %s AND user_id = %s",
                    (body.class_id, user["sub"]))
        r = cur.fetchone()
        if not r or r[0] != "teacher":
            raise HTTPException(status_code=403, detail="Non sei docente di questa classe")

        published = []
        for lid in body.lesson_ids[:40]:
            cur.execute("SELECT title, created_by FROM academy_lessons WHERE id = %s", (lid,))
            lr = cur.fetchone()
            if not lr:
                continue
            if str(lr[1]) != user["sub"] and not _is_admin(user["sub"]):
                raise HTTPException(status_code=403, detail="Puoi assegnare solo le tue lezioni")
            cur.execute("UPDATE academy_lessons SET status = 'published', updated_at = NOW() WHERE id = %s", (lid,))
            title = _j(lr[0])
            text = title.get("it") or title.get("en") or "Lezione"
            extra = []
            if body.note:
                extra.append(body.note.strip())
            if body.due:
                extra.append(f"Consegna: {body.due.strip()}")
            if extra:
                text += " — " + " · ".join(extra)
            cur.execute("""INSERT INTO class_posts (class_id, author_id, kind, text, lesson_id)
                           VALUES (%s, %s, 'lesson', %s, %s)""",
                        (body.class_id, user["sub"], text[:500], lid))
            published.append(lid)
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"status": "ok", "published": published}
