-- Run this in Supabase SQL editor to create the usage_logs table

CREATE TABLE IF NOT EXISTS usage_logs (
  id                uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  call_sid          text,
  service           text        NOT NULL,   -- 'gemini_live' | 'vobiz' | 'openrouter'
  model             text,                   -- model name / provider label
  audio_in_seconds  float,                  -- caller audio sent to Gemini (seconds)
  audio_out_seconds float,                  -- Gemini response audio (seconds)
  input_tokens      int,                    -- LLM prompt tokens (OpenRouter)
  output_tokens     int,                    -- LLM completion tokens (OpenRouter)
  duration_seconds  float,                  -- VoBiz call duration (seconds)
  cost_usd          float,                  -- estimated cost in USD
  created_at        timestamptz DEFAULT now()
);

-- Index for dashboard queries
CREATE INDEX IF NOT EXISTS usage_logs_created_at_idx ON usage_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS usage_logs_service_idx    ON usage_logs (service);
CREATE INDEX IF NOT EXISTS usage_logs_call_sid_idx   ON usage_logs (call_sid);
