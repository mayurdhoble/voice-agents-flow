-- Hotel Gem Park, Ooty — voice agent calls and callback verdicts.
-- Kept separate from the Lotus Sutra tables (calls, guests, bookings,
-- usage_logs) so the two hotels' data and revenue figures never mix.
-- Run this in the Supabase SQL editor.

CREATE TABLE IF NOT EXISTS gp_calls (
  id                 uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  call_sid           text,
  phone_number       text,
  started_at         timestamptz,
  ended_at           timestamptz,
  duration_seconds   float,
  recording_url      text,
  transcript         jsonb,                      -- [{role, content}, ...]

  -- Post-call review (second agent)
  call_back          boolean     DEFAULT false,  -- should the team call this guest back?
  lead_temperature   text,                       -- hot | warm | cold | unknown
  intent             text,                       -- room_booking | event | dining | information | other
  callback_promised  boolean     DEFAULT false,  -- Nora told the guest the team will reach out
  guest_name         text,
  dates_mentioned    text,
  guests             int,
  room_interest      text,
  interest_summary   text,
  call_summary       text,
  reason             text,                       -- why call back, or why not
  language           text,

  -- Follow-up tracking for the client and admin panels
  callback_status    text        DEFAULT 'pending',  -- pending | contacted | not_needed
  contacted_at       timestamptz,

  whatsapp_sent      boolean     DEFAULT false,
  gemini_cost_usd    float,
  vobiz_cost_usd     float,
  created_at         timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS gp_calls_created_at_idx ON gp_calls (created_at DESC);
CREATE INDEX IF NOT EXISTS gp_calls_callback_idx   ON gp_calls (call_back, callback_status);
CREATE INDEX IF NOT EXISTS gp_calls_phone_idx      ON gp_calls (phone_number);

-- WhatsApp conversations with the Gem Park bot. One row per guest number.
-- call_back is set when a guest shows booking interest over WhatsApp, so these
-- leads appear on the panels alongside the voice leads in gp_calls.
CREATE TABLE IF NOT EXISTS gp_whatsapp_sessions (
  phone             text        PRIMARY KEY,
  conversation      jsonb       DEFAULT '[]'::jsonb,   -- [{role, content, ts}, ...]
  call_back         boolean     DEFAULT false,
  interest_summary  text,
  callback_status   text,                              -- pending | contacted | not_needed
  contacted_at      timestamptz,
  last_message_at   timestamptz,
  created_at        timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS gp_whatsapp_sessions_callback_idx
  ON gp_whatsapp_sessions (call_back, callback_status);
