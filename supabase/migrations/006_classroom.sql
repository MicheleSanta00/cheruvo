-- ============================================================
-- Migration 006: Classroom (classi, membri, stream, chat) + ruolo profilo
-- Eseguire in Supabase SQL Editor.
--
-- Per il CARICAMENTO FILE serve un bucket Storage (vedi nota in fondo).
-- ============================================================

-- Ruolo docente/studente sul profilo Academy
alter table academy_profiles add column if not exists role text;

create table if not exists classes (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  join_code  text unique not null,
  owner_id   uuid not null,
  created_at timestamptz default now()
);

create table if not exists class_members (
  class_id  uuid references classes(id) on delete cascade,
  user_id   uuid not null,
  role      text not null default 'student',
  joined_at timestamptz default now(),
  primary key (class_id, user_id)
);

create table if not exists class_posts (
  id         uuid primary key default gen_random_uuid(),
  class_id   uuid references classes(id) on delete cascade,
  author_id  uuid not null,
  kind       text not null default 'announcement',
  text       text,
  url        text,
  file_name  text,
  lesson_id  uuid,
  created_at timestamptz default now()
);

create table if not exists class_messages (
  id         uuid primary key default gen_random_uuid(),
  class_id   uuid references classes(id) on delete cascade,
  user_id    uuid not null,
  body       text not null,
  created_at timestamptz default now()
);

create index if not exists idx_cmembers_user on class_members (user_id);
create index if not exists idx_cposts_class on class_posts (class_id, created_at);
create index if not exists idx_cmsg_class on class_messages (class_id, created_at);

-- RLS: l'accesso passa dal backend (service role lo bypassa). Abilitiamo come
-- difesa per gli accessi diretti dal client (che qui non usiamo).
alter table classes        enable row level security;
alter table class_members  enable row level security;
alter table class_posts    enable row level security;
alter table class_messages enable row level security;

-- ============================================================
-- CARICAMENTO FILE — da fare a mano in Supabase (una volta):
-- 1) Storage → New bucket → nome "class-files" → Public ✓ → Create.
-- 2) Storage → class-files → Policies → New policy → "Allow authenticated uploads":
--    operazione INSERT, ruolo authenticated. (La lettura è pubblica perché il bucket è public.)
-- ============================================================
