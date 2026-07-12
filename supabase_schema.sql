-- ─── Hotel Voice Agent — Supabase Schema ─────────────────────────────────────
-- Run this in Supabase SQL Editor (Database → SQL Editor → New Query)

-- Enable UUID generation
create extension if not exists "pgcrypto";

-- ─── calls ────────────────────────────────────────────────────────────────────
create table if not exists calls (
    id           uuid primary key default gen_random_uuid(),
    call_sid     text unique not null,
    phone_number text,
    direction    text check (direction in ('inbound', 'outbound')) default 'inbound',
    language     text default 'en',
    started_at   timestamptz,
    ended_at     timestamptz,
    transcript   jsonb,
    created_at   timestamptz default now()
);

-- ─── guests ───────────────────────────────────────────────────────────────────
create table if not exists guests (
    id                    uuid primary key default gen_random_uuid(),
    name                  text,
    phone                 text unique not null,
    email                 text,
    djubo_tracker_id      text,
    created_at            timestamptz default now(),
    updated_at            timestamptz default now()
);

-- ─── bookings ─────────────────────────────────────────────────────────────────
create table if not exists bookings (
    id               uuid primary key default gen_random_uuid(),
    call_sid         text references calls(call_sid) on delete set null,
    guest_id         uuid references guests(id) on delete set null,
    room_type        text,
    checkin_date     date,
    checkout_date    date,
    nights           integer,
    airport_pickup   boolean default false,
    extra_bed        boolean default false,
    status           text check (status in ('pending', 'confirmed', 'cancelled')) default 'pending',
    djubo_booking_id text,
    whatsapp_sent    boolean default false,
    created_at       timestamptz default now()
);

-- ─── events ───────────────────────────────────────────────────────────────────
create table if not exists events (
    id          uuid primary key default gen_random_uuid(),
    call_sid    text references calls(call_sid) on delete set null,
    guest_id    uuid references guests(id) on delete set null,
    event_type  text,
    event_date  date,
    num_guests  integer,
    status      text check (status in ('inquiry', 'confirmed', 'cancelled')) default 'inquiry',
    created_at  timestamptz default now()
);

-- ─── whatsapp_logs ────────────────────────────────────────────────────────────
create table if not exists whatsapp_logs (
    id            uuid primary key default gen_random_uuid(),
    booking_id    uuid references bookings(id) on delete set null,
    phone         text,
    template_name text,
    status        text check (status in ('sent', 'delivered', 'failed')),
    sent_at       timestamptz default now()
);
