-- Run this in Supabase → SQL Editor

create table if not exists requests (
  id           uuid primary key default gen_random_uuid(),
  call_sid     text,
  guest_id     uuid references guests(id) on delete set null,
  guest_name   text,
  request_type text not null,  -- airport_pickup, cab, extra_bed, early_checkin, late_checkout, restaurant, laundry, room_service, event, other
  details      text,
  date_needed  date,
  status       text not null default 'new',  -- new, acknowledged, handled
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists requests_call_sid_idx    on requests(call_sid);
create index if not exists requests_guest_id_idx    on requests(guest_id);
create index if not exists requests_status_idx      on requests(status);
create index if not exists requests_request_type_idx on requests(request_type);
create index if not exists requests_created_at_idx  on requests(created_at desc);
