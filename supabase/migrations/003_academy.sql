-- ============================================================
-- Migration 003: Cheruvo Academy
-- Sezione educativa (separata dalla home) + workspace admin.
-- Eseguire in Supabase SQL Editor.
--
-- Note:
--  * I testi (title/description/content) sono JSONB bilingui: {"it": "...", "en": "..."}.
--  * Il backend FastAPI accede col service role e BYPASSA la RLS: l'autorizzazione
--    vera la fanno gli endpoint (require_admin). La RLS qui sotto è difesa a strati
--    per eventuali accessi diretti via client.
-- ============================================================

-- ── Ruolo admin ─────────────────────────────────────────────
create table if not exists admins (
  user_id    uuid primary key,
  created_at timestamptz default now()
);

-- Helper riusato dalle policy RLS
create or replace function is_academy_admin()
returns boolean
language sql
security definer
as $$
  select exists (select 1 from admins where user_id = auth.uid());
$$;

-- ── Percorsi ────────────────────────────────────────────────
create table if not exists academy_paths (
  id          uuid primary key default gen_random_uuid(),
  slug        text unique not null,
  title       jsonb not null default '{}'::jsonb,   -- {"it","en"}
  description jsonb not null default '{}'::jsonb,
  cover_icon  text,
  sort_order  int default 0,
  published   boolean default false,
  created_at  timestamptz default now()
);

-- ── Lezioni-gioco ───────────────────────────────────────────
create table if not exists academy_lessons (
  id         uuid primary key default gen_random_uuid(),
  path_id    uuid references academy_paths(id) on delete cascade,
  type       text not null check (type in ('quiz','simulator','flashcard','scenario')),
  title      jsonb not null default '{}'::jsonb,     -- {"it","en"}
  content    jsonb not null default '{}'::jsonb,     -- schema per tipo
  sort_order int default 0,
  status     text not null default 'draft' check (status in ('draft','published')),
  created_by uuid,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index if not exists idx_lessons_path on academy_lessons (path_id, sort_order);

-- ── Progresso utente (login obbligatorio) ───────────────────
create table if not exists academy_progress (
  user_id      uuid not null,
  lesson_id    uuid references academy_lessons(id) on delete cascade,
  status       text default 'in_progress',
  score        int default 0,                        -- XP guadagnati per questa lezione
  completed_at timestamptz,
  primary key (user_id, lesson_id)
);
create index if not exists idx_progress_user on academy_progress (user_id);

-- ── Profilo Academy (nickname + opt-in classifica) ──────────
create table if not exists academy_profiles (
  user_id            uuid primary key,
  display_name       text,
  leaderboard_opt_in boolean default false,
  created_at         timestamptz default now()
);

-- ── RLS ─────────────────────────────────────────────────────
alter table academy_paths    enable row level security;
alter table academy_lessons  enable row level security;
alter table academy_progress enable row level security;
alter table academy_profiles enable row level security;

-- Percorsi/Lezioni: lettura per utenti autenticati solo se pubblicati (o admin); scrittura solo admin
drop policy if exists paths_read   on academy_paths;
create policy paths_read on academy_paths for select
  using (auth.role() = 'authenticated' and (published or is_academy_admin()));
drop policy if exists paths_write  on academy_paths;
create policy paths_write on academy_paths for all
  using (is_academy_admin()) with check (is_academy_admin());

drop policy if exists lessons_read  on academy_lessons;
create policy lessons_read on academy_lessons for select
  using (auth.role() = 'authenticated' and (status = 'published' or is_academy_admin()));
drop policy if exists lessons_write on academy_lessons;
create policy lessons_write on academy_lessons for all
  using (is_academy_admin()) with check (is_academy_admin());

-- Progresso: ognuno gestisce solo le proprie righe
drop policy if exists progress_own on academy_progress;
create policy progress_own on academy_progress for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Profilo: ognuno gestisce il proprio
drop policy if exists profiles_own on academy_profiles;
create policy profiles_own on academy_profiles for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ── Seed: un percorso + una lezione quiz pubblicata (bilingue) ──
insert into academy_paths (slug, title, description, cover_icon, sort_order, published)
values (
  'le-basi',
  $j${"it": "Le basi della finanza", "en": "Finance basics"}$j$::jsonb,
  $j${"it": "Azioni, ETF, rischio: il vocabolario per partire.", "en": "Stocks, ETFs, risk: the vocabulary to get started."}$j$::jsonb,
  'school', 0, true
)
on conflict (slug) do nothing;

insert into academy_lessons (path_id, type, title, content, sort_order, status)
select p.id, 'quiz',
  $j${"it": "Cos'è un ETF", "en": "What is an ETF"}$j$::jsonb,
  $j${
    "timer_sec": 30,
    "pass_score": 70,
    "questions": [
      {
        "q": {"it": "Cos'è un ETF?", "en": "What is an ETF?"},
        "options": [
          {"it": "Un singolo titolo azionario", "en": "A single stock"},
          {"it": "Un fondo che replica un indice", "en": "A fund that tracks an index"},
          {"it": "Un conto deposito vincolato", "en": "A locked savings account"},
          {"it": "Una criptovaluta", "en": "A cryptocurrency"}
        ],
        "correct": 1,
        "explain": {"it": "Un ETF raggruppa molti titoli e replica un indice: ti diversifichi con un solo strumento.", "en": "An ETF bundles many securities and tracks an index: you diversify with a single instrument."}
      },
      {
        "q": {"it": "Perché diversificare riduce il rischio?", "en": "Why does diversification reduce risk?"},
        "options": [
          {"it": "Perché garantisce guadagni", "en": "Because it guarantees gains"},
          {"it": "Perché un singolo crollo pesa meno sul totale", "en": "Because a single crash weighs less on the total"},
          {"it": "Perché elimina ogni rischio", "en": "Because it removes all risk"},
          {"it": "Perché aumenta le commissioni", "en": "Because it raises fees"}
        ],
        "correct": 1,
        "explain": {"it": "Spalmando il capitale su più titoli, il crollo di uno incide meno sul portafoglio totale.", "en": "By spreading capital across many holdings, one crash affects the whole portfolio less."}
      }
    ]
  }$j$::jsonb,
  0, 'published'
from academy_paths p
where p.slug = 'le-basi'
on conflict do nothing;

-- ── Diventa admin: sostituisci l'UUID con il tuo user_id Supabase ──
-- Lo trovi in Supabase → Authentication → Users (colonna UID).
-- insert into admins (user_id) values ('IL-TUO-USER-ID-UUID') on conflict do nothing;
