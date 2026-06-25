"""
classroom.py — Classi stile Classroom: classi, membri (codice d'invito), stream di
post (annunci/materiali/lezioni/file) e chat. Accesso solo previo login.
I file veri si caricano dal frontend su Supabase Storage; qui salviamo l'URL.
"""
import logging
import random
import string

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal

from database import get_pool
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/classroom")


def _conn():
    return get_pool().getconn()

def _rel(c):
    get_pool().putconn(c)


def init_classroom_tables():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name       TEXT NOT NULL,
                join_code  TEXT UNIQUE NOT NULL,
                owner_id   UUID NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS class_members (
                class_id  UUID REFERENCES classes(id) ON DELETE CASCADE,
                user_id   UUID NOT NULL,
                role      TEXT NOT NULL DEFAULT 'student',
                joined_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (class_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS class_posts (
                id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                class_id   UUID REFERENCES classes(id) ON DELETE CASCADE,
                author_id  UUID NOT NULL,
                kind       TEXT NOT NULL DEFAULT 'announcement',
                text       TEXT,
                url        TEXT,
                file_name  TEXT,
                lesson_id  UUID,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS class_messages (
                id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                class_id   UUID REFERENCES classes(id) ON DELETE CASCADE,
                user_id    UUID NOT NULL,
                body       TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_cmembers_user ON class_members (user_id);
            CREATE INDEX IF NOT EXISTS idx_cposts_class ON class_posts (class_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_cmsg_class ON class_messages (class_id, created_at);
        """)
        conn.commit()
        cur.close()
    finally:
        _rel(conn)


def _user_role(uid: str) -> str:
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role FROM academy_profiles WHERE user_id = %s", (uid,))
        r = cur.fetchone()
        cur.close()
    finally:
        _rel(conn)
    return (r[0] if r else None) or "student"


def _class_role(cid: str, uid: str):
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role FROM class_members WHERE class_id = %s AND user_id = %s", (cid, uid))
        r = cur.fetchone()
        cur.close()
    finally:
        _rel(conn)
    return r[0] if r else None


def _gen_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


class ClassIn(BaseModel):
    name: str

class JoinIn(BaseModel):
    code: str

class PostIn(BaseModel):
    kind: Literal["announcement", "material", "lesson", "file"] = "announcement"
    text: Optional[str] = None
    url: Optional[str] = None
    file_name: Optional[str] = None
    lesson_id: Optional[str] = None

class MsgIn(BaseModel):
    body: str


@router.post("/classes")
def create_class(body: ClassIn, user: dict = Depends(get_current_user)):
    if _user_role(user["sub"]) != "teacher":
        raise HTTPException(status_code=403, detail="Solo i docenti possono creare classi")
    name = (body.name or "").strip() or "Classe"
    conn = _conn()
    try:
        cur = conn.cursor()
        code = _gen_code()
        for _ in range(5):
            cur.execute("SELECT 1 FROM classes WHERE join_code = %s", (code,))
            if not cur.fetchone():
                break
            code = _gen_code()
        cur.execute("INSERT INTO classes (name, join_code, owner_id) VALUES (%s, %s, %s) RETURNING id",
                    (name, code, user["sub"]))
        cid = cur.fetchone()[0]
        cur.execute("INSERT INTO class_members (class_id, user_id, role) VALUES (%s, %s, 'teacher')",
                    (cid, user["sub"]))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"id": str(cid), "join_code": code}


@router.get("/classes")
def my_classes(user: dict = Depends(get_current_user)):
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.id, c.name, c.join_code, m.role,
                   (SELECT count(*) FROM class_members x WHERE x.class_id = c.id)
            FROM classes c
            JOIN class_members m ON m.class_id = c.id AND m.user_id = %s
            ORDER BY c.created_at DESC
        """, (user["sub"],))
        rows = [{"id": str(r[0]), "name": r[1], "join_code": r[2], "role": r[3], "members": int(r[4])} for r in cur.fetchall()]
        cur.close()
    finally:
        _rel(conn)
    return {"classes": rows}


@router.post("/join")
def join_class(body: JoinIn, user: dict = Depends(get_current_user)):
    code = (body.code or "").strip().upper()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM classes WHERE join_code = %s", (code,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Codice non valido")
        cid = r[0]
        cur.execute("INSERT INTO class_members (class_id, user_id, role) VALUES (%s, %s, 'student') ON CONFLICT DO NOTHING",
                    (cid, user["sub"]))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"id": str(cid)}


@router.get("/classes/{cid}")
def get_class(cid: str, user: dict = Depends(get_current_user)):
    role = _class_role(cid, user["sub"])
    if not role:
        raise HTTPException(status_code=403, detail="Non sei membro di questa classe")
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, join_code, owner_id FROM classes WHERE id = %s", (cid,))
        c = cur.fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="Classe non trovata")
        cur.execute("""
            SELECT m.user_id, m.role, COALESCE(pr.display_name, u.email, 'Utente')
            FROM class_members m
            LEFT JOIN academy_profiles pr ON pr.user_id = m.user_id
            LEFT JOIN auth.users u ON u.id = m.user_id
            WHERE m.class_id = %s ORDER BY (m.role = 'teacher') DESC, m.joined_at
        """, (cid,))
        members = [{"user_id": str(r[0]), "role": r[1], "name": r[2]} for r in cur.fetchall()]
        cur.execute("""
            SELECT p.id, p.kind, p.text, p.url, p.file_name, p.lesson_id, p.created_at,
                   COALESCE(pr.display_name, u.email, 'Utente')
            FROM class_posts p
            LEFT JOIN academy_profiles pr ON pr.user_id = p.author_id
            LEFT JOIN auth.users u ON u.id = p.author_id
            WHERE p.class_id = %s ORDER BY p.created_at DESC
        """, (cid,))
        posts = [{"id": str(r[0]), "kind": r[1], "text": r[2], "url": r[3], "file_name": r[4],
                  "lesson_id": str(r[5]) if r[5] else None,
                  "created_at": r[6].isoformat() if r[6] else None, "author": r[7]} for r in cur.fetchall()]
        cur.close()
    finally:
        _rel(conn)
    return {"id": str(c[0]), "name": c[1], "join_code": c[2],
            "is_teacher": role == "teacher", "my_role": role, "members": members, "posts": posts}


@router.post("/classes/{cid}/posts")
def create_post(cid: str, body: PostIn, user: dict = Depends(get_current_user)):
    if _class_role(cid, user["sub"]) != "teacher":
        raise HTTPException(status_code=403, detail="Solo il docente può pubblicare")
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO class_posts (class_id, author_id, kind, text, url, file_name, lesson_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (cid, user["sub"], body.kind, body.text, body.url, body.file_name, body.lesson_id))
        pid = cur.fetchone()[0]
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"id": str(pid)}


@router.delete("/posts/{pid}")
def delete_post(pid: str, user: dict = Depends(get_current_user)):
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT class_id, author_id FROM class_posts WHERE id = %s", (pid,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Post non trovato")
        if str(r[1]) != user["sub"] and _class_role(r[0], user["sub"]) != "teacher":
            raise HTTPException(status_code=403, detail="Non autorizzato")
        cur.execute("DELETE FROM class_posts WHERE id = %s", (pid,))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"status": "ok"}


@router.get("/classes/{cid}/messages")
def get_messages(cid: str, user: dict = Depends(get_current_user)):
    if not _class_role(cid, user["sub"]):
        raise HTTPException(status_code=403, detail="Non sei membro")
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT m.id, m.user_id, m.body, m.created_at, COALESCE(pr.display_name, u.email, 'Utente')
            FROM class_messages m
            LEFT JOIN academy_profiles pr ON pr.user_id = m.user_id
            LEFT JOIN auth.users u ON u.id = m.user_id
            WHERE m.class_id = %s ORDER BY m.created_at ASC LIMIT 200
        """, (cid,))
        msgs = [{"id": str(r[0]), "user_id": str(r[1]), "body": r[2],
                 "created_at": r[3].isoformat() if r[3] else None, "name": r[4],
                 "is_me": str(r[1]) == user["sub"]} for r in cur.fetchall()]
        cur.close()
    finally:
        _rel(conn)
    return {"messages": msgs}


@router.post("/classes/{cid}/messages")
def send_message(cid: str, body: MsgIn, user: dict = Depends(get_current_user)):
    if not _class_role(cid, user["sub"]):
        raise HTTPException(status_code=403, detail="Non sei membro")
    b = (body.body or "").strip()
    if not b:
        raise HTTPException(status_code=400, detail="Messaggio vuoto")
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO class_messages (class_id, user_id, body) VALUES (%s, %s, %s)",
                    (cid, user["sub"], b[:2000]))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"status": "ok"}


@router.post("/classes/{cid}/leave")
def leave_class(cid: str, user: dict = Depends(get_current_user)):
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT owner_id FROM classes WHERE id = %s", (cid,))
        r = cur.fetchone()
        if r and str(r[0]) == user["sub"]:
            raise HTTPException(status_code=400, detail="Il proprietario non può lasciare la classe")
        cur.execute("DELETE FROM class_members WHERE class_id = %s AND user_id = %s", (cid, user["sub"]))
        conn.commit()
        cur.close()
    finally:
        _rel(conn)
    return {"status": "ok"}
