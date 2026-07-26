-- Run in Supabase → SQL Editor

create table if not exists whatsapp_sessions (
  id               uuid primary key default gen_random_uuid(),
  phone            text not null unique,
  guest_name       text,
  conversation     jsonb not null default '[]',
  booking_done     boolean not null default false,
  last_message_at  timestamptz not null default now(),
  created_at       timestamptz not null default now()
);

create index if not exists whatsapp_sessions_phone_idx          on whatsapp_sessions(phone);
create index if not exists whatsapp_sessions_last_message_idx   on whatsapp_sessions(last_message_at desc);
