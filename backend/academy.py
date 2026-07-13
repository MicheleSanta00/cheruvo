"""
academy.py — Cheruvo Academy (sezione educativa + workspace admin).

Sezione separata dalla home. Accesso solo previo login (get_current_user).
Le scritture sui contenuti richiedono il ruolo admin (require_admin).
Tutti i testi (title/content) sono JSONB bilingui: {"it": "...", "en": "..."}.
"""

import os
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from typing import Literal, Optional

from database import get_pool
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/academy")

# XP assegnati lato server (no fiducia nel client)
XP_COMPLETE = 50
XP_PER_CORRECT = 20


# ── Helpers DB ──────────────────────────────────────────────────────────────
def _conn():
    return get_pool().getconn()

def _rel(conn):
    get_pool().putconn(conn)

def _j(v):
    """jsonb → dict: psycopg2 a volte ritorna str, a volte dict. Normalizza."""
    if v is None:
        return {}
    return json.loads(v) if isinstance(v, str) else v


def init_academy_tables():
    """Crea le tabelle se non esistono (idempotente). La RLS è nella migration 003."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id    UUID PRIMARY KEY,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS academy_paths (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                slug        TEXT UNIQUE NOT NULL,
                title       JSONB NOT NULL DEFAULT '{}'::jsonb,
                description JSONB NOT NULL DEFAULT '{}'::jsonb,
                cover_icon  TEXT,
                sort_order  INT DEFAULT 0,
                published   BOOLEAN DEFAULT FALSE,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS academy_lessons (
                id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                path_id    UUID REFERENCES academy_paths(id) ON DELETE CASCADE,
                type       TEXT NOT NULL CHECK (type IN ('quiz','simulator','flashcard','scenario')),
                title      JSONB NOT NULL DEFAULT '{}'::jsonb,
                content    JSONB NOT NULL DEFAULT '{}'::jsonb,
                sort_order INT DEFAULT 0,
                status     TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published')),
                created_by UUID,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS academy_progress (
                user_id      UUID NOT NULL,
                lesson_id    UUID REFERENCES academy_lessons(id) ON DELETE CASCADE,
                status       TEXT DEFAULT 'in_progress',
                score        INT DEFAULT 0,
                completed_at TIMESTAMPTZ,
                PRIMARY KEY (user_id, lesson_id)
            );
            CREATE TABLE IF NOT EXISTS academy_profiles (
                user_id            UUID PRIMARY KEY,
                display_name       TEXT,
                leaderboard_opt_in BOOLEAN DEFAULT FALSE,
                created_at         TIMESTAMPTZ DEFAULT NOW()
            );
            ALTER TABLE academy_lessons ADD COLUMN IF NOT EXISTS level TEXT DEFAULT 'base';
            ALTER TABLE academy_profiles ADD COLUMN IF NOT EXISTS role TEXT;
            -- 'global' = contenuto Academy (admin), 'class' = creato da un docente per le sue classi
            ALTER TABLE academy_lessons ADD COLUMN IF NOT EXISTS visibility TEXT DEFAULT 'global';
        """)
        conn.commit()
        cur.close()
    finally:
        _rel(conn)


# ── Autorizzazione admin ────────────────────────────────────────────────────
def _is_admin(user_id: str) -> bool:
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM admins WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
    finally:
        _rel(conn)
    return row is not None


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not _is_admin(user["sub"]):
        raise HTTPException(status_code=403, detail="Riservato agli amministratori")
    return user


# ── Modelli Pydantic ────────────────────────────────────────────────────────
class Localized(BaseModel):
    it: str = ""
    en: str = ""

class QuizQuestion(BaseModel):
    q: Localized
    options: list[Localized]
    correct: int
    explain: Optional[Localized] = None

class QuizContent(BaseModel):
    timer_sec: int = 30
    pass_score: int = 70
    questions: list[QuizQuestion]

class LessonIn(BaseModel):
    path_id: Optional[str] = None
    type: Literal["quiz", "simulator", "flashcard", "scenario"]
    title: Localized
    content: dict
    sort_order: int = 0
    status: Literal["draft", "published"] = "draft"
    level: str = "base"

class ProgressIn(BaseModel):
    lesson_id: str
    correct: int = 0          # risposte corrette (per calcolare XP lato server)
    completed: bool = True

class ProfileIn(BaseModel):
    display_name: Optional[str] = None
    leaderboard_opt_in: bool = False
    role: Optional[str] = None

class AIDraftIn(BaseModel):
    topic: str
    type: str = "quiz"
    n: int = 5


# Simulatore (i parametri/calcoli vivono nel frontend; qui validiamo modello + testo)
SIM_MODELS = {"compound_interest", "pac", "inflation", "budget_50_30_20"}

class SimulatorContent(BaseModel):
    model: str
    teach: Localized = Field(default_factory=Localized)

# Flashcard
class Flashcard(BaseModel):
    term: Localized
    definition: Localized
    example: Optional[Localized] = None

class FlashcardContent(BaseModel):
    deck: list[Flashcard]

# Scenario (storia a bivi)
class ScenarioChoice(BaseModel):
    label: Localized
    feedback: Localized = Field(default_factory=Localized)
    goto: str = ""   # id del nodo successivo, "" = fine

class ScenarioNode(BaseModel):
    text: Localized
    choices: list[ScenarioChoice]

class ScenarioContent(BaseModel):
    start: str
    ticker: Optional[str] = None
    nodes: dict[str, ScenarioNode]


def _validate_content(ltype: str, content: dict) -> dict:
    """Valida e normalizza il content in base al tipo (422 se non valido)."""
    try:
        if ltype == "quiz":
            return QuizContent(**content).model_dump()
        if ltype == "simulator":
            c = SimulatorContent(**content)
            if c.model not in SIM_MODELS:
                raise ValueError("modello simulatore non valido")
            return c.model_dump()
        if ltype == "flashcard":
            return FlashcardContent(**content).model_dump()
        if ltype == "scenario":
            return ScenarioContent(**content).model_dump()
        return content
    except (ValidationError, ValueError) as e:
        raise HTTPException(status_code=422, detail="Contenuto non valido: " + str(e)[:200])


# ── Endpoint studente (login richiesto) ─────────────────────────────────────
@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT display_name, leaderboard_opt_in, role FROM academy_profiles WHERE user_id = %s", (user["sub"],))
        row = cur.fetchone()
        cur.close()
    finally:
        _rel(conn)
    profile = {"display_name": row[0], "leaderboard_opt_in": row[1], "role": row[2]} if row else {"display_name": None, "leaderboard_opt_in": False, "role": None}
    return {"is_admin": _is_admin(user["sub"]), "profile": profile}


@router.put("/me")
def update_me(body: ProfileIn, user: dict = Depends(get_current_user)):
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO academy_profiles (user_id, display_name, leaderboard_opt_in, role)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
              SET display_name = EXCLUDED.display_name,
                  leaderboard_opt_in = EXCLUDED.leaderboard_opt_in,
                  role = COALESCE(EXCLUDED.role, academy_profiles.role)
        """, (user["sub"], body.display_name, body.leaderboard_opt_in, body.role))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"status": "ok"}


@router.get("/paths")
def list_paths(user: dict = Depends(get_current_user)):
    """Percorsi pubblicati + lezioni pubblicate + stato di completamento dell'utente."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, slug, title, description, cover_icon, sort_order
            FROM academy_paths WHERE published = TRUE ORDER BY sort_order, created_at
        """)
        paths = [{"id": r[0], "slug": r[1], "title": _j(r[2]), "description": _j(r[3]),
                  "cover_icon": r[4], "sort_order": r[5], "lessons": []} for r in cur.fetchall()]
        by_id = {p["id"]: p for p in paths}

        cur.execute("""
            SELECT l.id, l.path_id, l.type, l.title, l.sort_order, l.level,
                   COALESCE(pg.status, '') AS pstatus
            FROM academy_lessons l
            LEFT JOIN academy_progress pg
              ON pg.lesson_id = l.id AND pg.user_id = %s
            WHERE l.status = 'published'
              AND COALESCE(l.visibility, 'global') = 'global'
            ORDER BY l.sort_order, l.created_at
        """, (user["sub"],))
        for r in cur.fetchall():
            p = by_id.get(r[1])
            if p:
                p["lessons"].append({"id": r[0], "type": r[2], "title": _j(r[3]),
                                     "sort_order": r[4], "level": r[5] or "base", "completed": r[6] == "done"})
        cur.close()
    finally:
        _rel(conn)
    return {"paths": paths}


@router.get("/lessons/{lesson_id}")
def get_lesson(lesson_id: str, user: dict = Depends(get_current_user)):
    """Accesso: contenuto 'global' pubblicato → tutti; contenuto 'class' → il
    docente che l'ha creato sempre, gli studenti se è pubblicato e assegnato
    (post) in una classe di cui sono membri; gli admin sempre."""
    is_admin = _is_admin(user["sub"])
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT id, path_id, type, title, content, status, level,
                              COALESCE(visibility, 'global'), created_by
                       FROM academy_lessons WHERE id = %s""", (lesson_id,))
        row = cur.fetchone()
        assigned = False
        if row and row[7] == "class":
            cur.execute("""
                SELECT 1 FROM class_posts p
                JOIN class_members m ON m.class_id = p.class_id AND m.user_id = %s
                WHERE p.lesson_id = %s LIMIT 1
            """, (user["sub"], lesson_id))
            assigned = cur.fetchone() is not None
        cur.close()
    finally:
        _rel(conn)
    if not row:
        raise HTTPException(status_code=404, detail="Lezione non trovata")
    is_owner = row[8] is not None and str(row[8]) == user["sub"]
    visibility = row[7]
    allowed = (
        is_admin or is_owner
        or (visibility == "global" and row[5] == "published")
        or (visibility == "class" and row[5] == "published" and assigned)
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Lezione non disponibile")
    return {"id": row[0], "path_id": row[1], "type": row[2], "title": _j(row[3]),
            "content": _j(row[4]), "status": row[5], "level": row[6] or "base",
            "visibility": visibility}


@router.post("/progress")
def save_progress(body: ProgressIn, user: dict = Depends(get_current_user)):
    """Salva il progresso e calcola gli XP lato server."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT type FROM academy_lessons WHERE id = %s AND status = 'published'", (body.lesson_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Lezione non trovata")
        xp = (XP_COMPLETE if body.completed else 0) + max(0, body.correct) * XP_PER_CORRECT
        cur.execute("""
            INSERT INTO academy_progress (user_id, lesson_id, status, score, completed_at)
            VALUES (%s, %s, %s, %s, CASE WHEN %s THEN NOW() ELSE NULL END)
            ON CONFLICT (user_id, lesson_id) DO UPDATE
              SET status = EXCLUDED.status,
                  score = GREATEST(academy_progress.score, EXCLUDED.score),
                  completed_at = COALESCE(academy_progress.completed_at, EXCLUDED.completed_at)
        """, (user["sub"], body.lesson_id, "done" if body.completed else "in_progress",
              xp, body.completed))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"status": "ok", "xp": xp}


@router.get("/leaderboard")
def leaderboard(range: str = "all", user: dict = Depends(get_current_user)):
    where = ""
    if range == "week":
        where = "AND pg.completed_at >= date_trunc('week', now())"
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT pr.user_id, COALESCE(pr.display_name, 'Anonimo') AS name, SUM(pg.score) AS xp
            FROM academy_progress pg
            JOIN academy_profiles pr ON pr.user_id = pg.user_id AND pr.leaderboard_opt_in = TRUE
            WHERE pg.score > 0 {where}
            GROUP BY pr.user_id, pr.display_name
            ORDER BY xp DESC
            LIMIT 20
        """)
        top = [{"rank": i + 1, "name": r[1], "xp": int(r[2]),
                "is_you": str(r[0]) == user["sub"]} for i, r in enumerate(cur.fetchall())]
        cur.close()
    finally:
        _rel(conn)
    return {"leaderboard": top, "range": range}


@router.get("/my/lessons")
def my_lessons(user: dict = Depends(get_current_user)):
    """Le lezioni create dall'utente (docente): per il wizard 'Lezioni dal libro'
    e per assegnarle in classe. Ordinate dalla più recente."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, type, title, status, level, created_at
            FROM academy_lessons
            WHERE created_by = %s AND COALESCE(visibility,'global') = 'class'
            ORDER BY created_at DESC LIMIT 200
        """, (user["sub"],))
        rows = [{"id": r[0], "type": r[1], "title": _j(r[2]), "status": r[3],
                 "level": r[4] or "base"} for r in cur.fetchall()]
        cur.close()
    finally:
        _rel(conn)
    return {"lessons": rows}


# ── Endpoint workspace (admin) ──────────────────────────────────────────────
@router.get("/admin/lessons")
def admin_list_lessons(user: dict = Depends(require_admin)):
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, path_id, type, title, status, sort_order, level
            FROM academy_lessons ORDER BY sort_order, created_at
        """)
        rows = [{"id": r[0], "path_id": r[1], "type": r[2], "title": _j(r[3]),
                 "status": r[4], "sort_order": r[5], "level": r[6] or "base"} for r in cur.fetchall()]
        cur.close()
    finally:
        _rel(conn)
    return {"lessons": rows}


@router.post("/lessons")
def create_lesson(body: LessonIn, user: dict = Depends(require_admin)):
    content = _validate_content(body.type, body.content)
    path_id = body.path_id
    conn = _conn()
    try:
        cur = conn.cursor()
        if not path_id:
            cur.execute("SELECT id FROM academy_paths ORDER BY sort_order LIMIT 1")
            r = cur.fetchone()
            path_id = r[0] if r else None
        cur.execute("""
            INSERT INTO academy_lessons (path_id, type, title, content, sort_order, status, level, created_by)
            VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
            RETURNING id
        """, (path_id, body.type, json.dumps(body.title.model_dump()), json.dumps(content),
              body.sort_order, body.status, body.level, user["sub"]))
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"id": new_id, "status": "created"}


def _require_lesson_owner(lesson_id: str, user: dict):
    """Admin: sempre. Docente: solo le lezioni create da lui (visibility 'class')."""
    if _is_admin(user["sub"]):
        return
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT created_by, COALESCE(visibility,'global') FROM academy_lessons WHERE id = %s", (lesson_id,))
        r = cur.fetchone()
        cur.close()
    finally:
        _rel(conn)
    if not r:
        raise HTTPException(status_code=404, detail="Lezione non trovata")
    if r[1] != "class" or r[0] is None or str(r[0]) != user["sub"]:
        raise HTTPException(status_code=403, detail="Puoi modificare solo le lezioni create da te")


@router.put("/lessons/{lesson_id}")
def update_lesson(lesson_id: str, body: LessonIn, user: dict = Depends(get_current_user)):
    _require_lesson_owner(lesson_id, user)
    content = _validate_content(body.type, body.content)
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE academy_lessons
               SET title = %s::jsonb, content = %s::jsonb, type = %s,
                   sort_order = %s, status = %s, level = %s, updated_at = NOW()
             WHERE id = %s
        """, (json.dumps(body.title.model_dump()), json.dumps(content), body.type,
              body.sort_order, body.status, body.level, lesson_id))
        updated = cur.rowcount
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    if not updated:
        raise HTTPException(status_code=404, detail="Lezione non trovata")
    return {"status": "updated"}


@router.delete("/lessons/{lesson_id}")
def delete_lesson(lesson_id: str, user: dict = Depends(get_current_user)):
    _require_lesson_owner(lesson_id, user)
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM academy_lessons WHERE id = %s", (lesson_id,))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"status": "deleted"}


class AddAdminIn(BaseModel):
    email: str


@router.get("/admin/admins")
def list_admins(user: dict = Depends(require_admin)):
    """Elenca gli admin con la loro email (join su auth.users)."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT a.user_id, u.email
            FROM admins a
            LEFT JOIN auth.users u ON u.id = a.user_id
            ORDER BY a.created_at
        """)
        rows = [{"user_id": str(r[0]), "email": r[1] or "—"} for r in cur.fetchall()]
        cur.close()
    finally:
        _rel(conn)
    return {"admins": rows}


@router.post("/admin/admins")
def add_admin(body: AddAdminIn, user: dict = Depends(require_admin)):
    """Promuove ad admin un utente cercandolo per email (deve aver già fatto login)."""
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email mancante")
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, email FROM auth.users WHERE lower(email) = %s", (email,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail="Nessun utente con questa email. Deve prima registrarsi e accedere almeno una volta.",
            )
        cur.execute("INSERT INTO admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (row[0],))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"status": "ok", "email": row[1]}


@router.delete("/admin/admins/{uid}")
def remove_admin(uid: str, user: dict = Depends(require_admin)):
    if uid == user["sub"]:
        raise HTTPException(status_code=400, detail="Non puoi rimuovere te stesso (eviti di restare senza admin).")
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM admins WHERE user_id = %s", (uid,))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"status": "ok"}


_AI_SCHEMAS = {
    "quiz": '{"questions":[{"q":{"it":"","en":""},"options":[{"it":"","en":""},{"it":"","en":""},{"it":"","en":""},{"it":"","en":""}],"correct":<indice 0-3>,"explain":{"it":"","en":""}}]}',
    "flashcard": '{"deck":[{"term":{"it":"","en":""},"definition":{"it":"","en":""},"example":{"it":"","en":""}}]}',
    "scenario": '{"start":"n1","nodes":{"n1":{"text":{"it":"","en":""},"choices":[{"label":{"it":"","en":""},"feedback":{"it":"","en":""},"goto":"n2 oppure stringa vuota per finire"}]}}}',
    "simulator": '{"model":"uno tra: compound_interest, pac, inflation, budget_50_30_20","teach":{"it":"","en":""}}',
}
_AI_ASK = {
    "quiz": "Genera {n} domande a risposta multipla (4 opzioni ciascuna) su: {topic}.",
    "flashcard": "Genera {n} flashcard (termine, definizione, esempio) su: {topic}.",
    "scenario": "Genera una breve storia a bivi (2-3 scene, id nodo n1/n2/...) di educazione finanziaria su: {topic}.",
    "simulator": "Scegli il modello più adatto e scrivi una spiegazione 'in parole povere' su: {topic}.",
}


@router.post("/ai/draft")
def ai_draft(body: AIDraftIn, user: dict = Depends(require_admin)):
    """Genera una bozza bilingue (IT/EN) via Groq per il tipo richiesto. L'admin la rivede e pubblica."""
    t = body.type if body.type in _AI_SCHEMAS else "quiz"
    n = max(1, min(body.n, 10))
    from groq import Groq
    client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
    system = (
        "Sei un autore di educazione finanziaria per investitori retail. "
        "Rispondi SOLO con JSON valido, senza testo extra. Tutti i testi sono bilingui "
        "{\"it\":\"...\",\"en\":\"...\"}. Linguaggio semplice, niente consigli di investimento. "
        "Schema da seguire: " + _AI_SCHEMAS[t]
    )
    prompt = _AI_ASK[t].format(n=n, topic=body.topic)
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
            max_tokens=2200,
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return _validate_content(t, data)   # valida/normalizza come un salvataggio
    except HTTPException:
        raise
    except Exception as e:
        logger.error("AI draft error: %s", e)
        raise HTTPException(status_code=503, detail="Generazione AI non riuscita, riprova")
