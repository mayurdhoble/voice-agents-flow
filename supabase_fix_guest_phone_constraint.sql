-- Run in Supabase → SQL Editor
-- Drops the unique constraint on guests.phone so multiple guests with
-- phone="unknown" (VoBiz not sending caller number) can coexist.

alter table guests drop constraint if exists guests_phone_key;
