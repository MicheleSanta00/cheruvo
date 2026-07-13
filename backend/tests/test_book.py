"""
test_book.py — "Lezioni dal Libro": autorizzazione docente, upload,
rilevamento capitoli, validazioni di generate/publish e permessi
sulle lezioni dei docenti.

Come test_auth.py: app minimale (solo router academy + book) con
dependency_overrides, senza importare main (evita pandas/yfinance pesanti
a runtime nei singoli test — database.py li importa comunque una volta).
"""
import sys, os, io, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DATABASE_URL", "postgresql://fake:fake@localhost/fake")
os.environ.setdefault("GROQ_API_KEY", "gsk_fake_key_for_tests")
os.environ.setdefault("BOOK_TMP_DIR", "/tmp/cheruvo_books_test")

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

TEACHER = {"sub": "11111111-1111-1111-1111-111111111111", "email": "prof@example.com"}
STUDENT = {"sub": "22222222-2222-2222-2222-222222222222", "email": "alunno@example.com"}


def _make_pool(fetchone=None, fetchall=None):
    pool, conn, cur = MagicMock(), MagicMock(), MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall or []
    pool.getconn.return_value = conn
    return pool, conn, cur


@pytest.fixture(scope="module")
def app():
    pool, _, _ = _make_pool()
    with patch("database.get_pool", return_value=pool):
        from academy import router as academy_router
        from book import router as book_router
        _app = FastAPI()
        _app.include_router(academy_router, prefix="/api")
        _app.include_router(book_router, prefix="/api")
        yield _app
        _app.dependency_overrides.clear()


def _as_user(app, user):
    from auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user


# ── require_teacher ─────────────────────────────────────────────────────────

class TestRequireTeacher:

    def test_studente_non_puo_usare_il_wizard(self, app):
        _as_user(app, STUDENT)
        pool, _, _ = _make_pool(fetchone=None)   # nessun ruolo, nessun admin
        with patch("book.get_pool", return_value=pool), \
             patch("academy.get_pool", return_value=pool):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post("/api/academy/book/upload",
                              files=[("files", ("cap.pdf", b"%PDF-1.4 fake", "application/pdf"))])
        assert resp.status_code == 403
        assert "docenti" in resp.json()["detail"].lower()

    def test_upload_richiede_login(self, app):
        app.dependency_overrides.clear()
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/academy/book/upload",
                          files=[("files", ("cap.pdf", b"%PDF", "application/pdf"))])
        assert resp.status_code in (401, 403)


# ── Upload: formati e limiti ────────────────────────────────────────────────

class TestUpload:

    @pytest.fixture(autouse=True)
    def setup(self, app):
        _as_user(app, TEACHER)
        yield
        app.dependency_overrides.clear()

    def test_formato_non_supportato(self, app):
        with patch("book._is_teacher", return_value=True):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post("/api/academy/book/upload",
                              files=[("files", ("appunti.txt", b"ciao", "text/plain"))])
        assert resp.status_code == 415

    def test_due_pdf_rifiutati(self, app):
        with patch("book._is_teacher", return_value=True):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post("/api/academy/book/upload", files=[
                    ("files", ("a.pdf", b"%PDF-1.4", "application/pdf")),
                    ("files", ("b.pdf", b"%PDF-1.4", "application/pdf")),
                ])
        assert resp.status_code == 400

    def test_pdf_vero_crea_job_ed_estrae_indice(self, app, tmp_path):
        """Upload di un PDF reale (PyMuPDF): il job viene creato e l'estrazione
        in background produce un indice senza chiamare l'LLM (c'è testo)."""
        fitz = pytest.importorskip("fitz")
        doc = fitz.open()
        for n in (1, 2):
            page = doc.new_page()
            page.insert_text((72, 72), f"Capitolo {n} - Argomento {n}", fontsize=18)
            page.insert_text((72, 110), ("La finanza studia come le persone allocano risorse nel tempo. " * 8))
        pdf_bytes = doc.tobytes()
        doc.close()

        job_id = "33333333-3333-3333-3333-333333333333"
        pool, _, cur = _make_pool(fetchone=(job_id,))
        updates = []
        with patch("book.get_pool", return_value=pool), \
             patch("book._is_teacher", return_value=True), \
             patch("book._upd", side_effect=lambda jid, **kw: updates.append(kw)):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post("/api/academy/book/upload",
                              files=[("files", ("libro.pdf", pdf_bytes, "application/pdf"))])
        assert resp.status_code == 200
        assert resp.json()["job_id"] == job_id
        # il background task (eseguito dal TestClient) è arrivato a 'ready' con un toc
        finali = [u for u in updates if u.get("status") == "ready"]
        assert finali and finali[0]["toc"], f"estrazione non completata: {updates[-3:]}"
        assert len(finali[0]["toc"]) == 2                      # 2 capitoli rilevati
        assert "Capitolo 1" in finali[0]["toc"][0]["title"]


# ── Rilevamento capitoli (euristica) ────────────────────────────────────────

class TestDetectChapters:

    def test_trova_capitoli_numerati(self):
        from book import _detect_chapters_from_text
        pages = [
            "CAPITOLO 1 — Il mercato\ntesto...",
            "altro testo senza intestazione",
            "Capitolo 2: La moneta\ntesto...",
            "coda",
        ]
        ch = _detect_chapters_from_text(pages)
        assert [c["start"] for c in ch] == [0, 2]
        assert ch[0]["end"] == 1 and ch[1]["end"] == 3

    def test_un_solo_capitolo_non_basta(self):
        from book import _detect_chapters_from_text
        assert _detect_chapters_from_text(["Capitolo 1 — Unico", "testo"]) == []


# ── Generate: validazioni ───────────────────────────────────────────────────

class TestGenerate:

    @pytest.fixture(autouse=True)
    def setup(self, app):
        _as_user(app, TEACHER)
        yield
        app.dependency_overrides.clear()

    def _post(self, app, body):
        with TestClient(app, raise_server_exceptions=False) as c:
            return c.post("/api/academy/book/generate", json=body)

    def test_job_inesistente_404(self, app):
        with patch("book._is_teacher", return_value=True), \
             patch("book._get_job", return_value=None):
            resp = self._post(app, {"job_id": "x", "chapters": [0]})
        assert resp.status_code == 404

    def test_job_di_altri_403(self, app):
        job = {"id": "j", "user_id": STUDENT["sub"], "status": "ready", "toc": [{"idx": 0}], "params": {}, "result": {}}
        with patch("book._is_teacher", return_value=True), \
             patch("book._get_job", return_value=job), \
             patch("book._is_admin", return_value=False):
            resp = self._post(app, {"job_id": "j", "chapters": [0]})
        assert resp.status_code == 403

    def test_job_non_pronto_409(self, app):
        job = {"id": "j", "user_id": TEACHER["sub"], "status": "extracting", "toc": [], "params": {}, "result": {}}
        with patch("book._is_teacher", return_value=True), \
             patch("book._get_job", return_value=job):
            resp = self._post(app, {"job_id": "j", "chapters": [0]})
        assert resp.status_code == 409

    def test_capitolo_inesistente_400(self, app):
        job = {"id": "j", "user_id": TEACHER["sub"], "status": "ready", "toc": [{"idx": 0}], "params": {}, "result": {}}
        with patch("book._is_teacher", return_value=True), \
             patch("book._get_job", return_value=job):
            resp = self._post(app, {"job_id": "j", "chapters": [7]})
        assert resp.status_code == 400


# ── Publish: solo il docente della classe, solo lezioni proprie ─────────────

class TestPublish:

    def test_non_docente_della_classe_403(self, app):
        _as_user(app, TEACHER)
        pool, _, cur = _make_pool(fetchone=None)   # non membro della classe
        with patch("book.get_pool", return_value=pool), \
             patch("book._is_teacher", return_value=True):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post("/api/academy/book/publish",
                              json={"lesson_ids": ["l1"], "class_id": "c1"})
        assert resp.status_code == 403
        app.dependency_overrides.clear()


# ── Permessi lezioni docente (academy.py) ───────────────────────────────────

class TestLessonOwnership:

    def test_docente_non_modifica_lezioni_altrui(self, app):
        _as_user(app, TEACHER)
        # la lezione esiste ma è di un altro (created_by diverso, visibility class)
        pool, _, cur = _make_pool(fetchone=(STUDENT["sub"], "class"))
        body = {"type": "quiz", "title": {"it": "x", "en": "x"},
                "content": {"questions": [{"q": {"it": "d", "en": "q"},
                                           "options": [{"it": "a", "en": "a"}, {"it": "b", "en": "b"}],
                                           "correct": 0}]},
                "status": "draft", "level": "base"}
        with patch("academy.get_pool", return_value=pool), \
             patch("academy._is_admin", return_value=False):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.put("/api/academy/lessons/abc", json=body)
        assert resp.status_code == 403
        app.dependency_overrides.clear()

    def test_lezione_globale_non_modificabile_dal_docente(self, app):
        _as_user(app, TEACHER)
        pool, _, cur = _make_pool(fetchone=(TEACHER["sub"], "global"))
        with patch("academy.get_pool", return_value=pool), \
             patch("academy._is_admin", return_value=False):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.delete("/api/academy/lessons/abc")
        assert resp.status_code == 403
        app.dependency_overrides.clear()
