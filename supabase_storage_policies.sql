-- ─── Supabase Storage — call recordings ──────────────────────────────────────
-- The app records each call itself (guest + Maya audio mixed to a WAV) and
-- uploads it to the `recordings` bucket via services in main.py.
--
-- Symptom this fixes:
--   [VB-G] Recording upload failed: {'statusCode': 403,
--          'message': new row violates row-level security policy}
--
-- ── Preferred fix (no SQL needed) ────────────────────────────────────────────
-- Set SUPABASE_KEY on Railway to the project's `service_role` secret key
-- (Supabase → Settings → API → service_role). It bypasses Storage RLS entirely.
-- This is the normal choice for a backend-only server. If you do that, you do
-- NOT need the policies below.
--
-- ── Alternative fix (keep the current anon key) ──────────────────────────────
-- 1. Create the bucket if it doesn't exist:
--      Storage → New bucket → name: recordings
-- 2. Make it Public (so get_public_url links open):
--      Storage → recordings → Configuration → Public bucket = ON
-- 3. Run the policies below in SQL Editor:

-- Allow uploading objects into the recordings bucket
create policy "recordings_insert"
on storage.objects for insert
to anon, authenticated
with check (bucket_id = 'recordings');

-- Allow reading objects back from the recordings bucket
create policy "recordings_read"
on storage.objects for select
to anon, authenticated
using (bucket_id = 'recordings');

-- Allow overwriting an existing recording (upload uses upsert=true)
create policy "recordings_update"
on storage.objects for update
to anon, authenticated
using (bucket_id = 'recordings')
with check (bucket_id = 'recordings');
