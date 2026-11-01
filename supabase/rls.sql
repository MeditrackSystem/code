-- RLS disabled for prototype (anon full access). Enable + add policies for production.
-- (No policies needed for prototype.)
alter table public.users disable row level security;
alter table public.patients disable row level security;
alter table public.rfid_tags disable row level security;
alter table public.medical_records disable row level security;
alter table public.medication_orders disable row level security;
alter table public.medication_administrations disable row level security;
alter table public.scan_logs disable row level security;
alter table public.audit_logs disable row level security;
