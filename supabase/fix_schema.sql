-- ============================================================
-- MediTrack · schema repair
-- ============================================================
-- The live project was originally created with Supabase Auth, so the staff
-- columns below were declared as `uuid references auth.users(id)`.
-- MediTrack uses a plain public.users table with bigint ids, so:
--   * joins such as scan_logs -> users fail with PGRST200
--   * writes that send a numeric user id fail with 22P02
--
-- This script converts those columns to bigint and points them at
-- public.users. Existing values are discarded (they are all NULL or belong
-- to the old auth schema), so run it before collecting real data.
--
-- Run once in Supabase Dashboard -> SQL Editor -> New query -> Run.
-- ============================================================

-- 1. Drop the old foreign keys that involve the staff columns ---------------
do $$
declare
  r record;
begin
  for r in
    select c.conrelid::regclass::text as tbl, c.conname
    from pg_constraint c
    join pg_attribute a
      on a.attrelid = c.conrelid
     and a.attnum = any (c.conkey)
    where c.contype = 'f'
      and (c.conrelid, a.attname) in (
        ('public.scan_logs'::regclass, 'user_id'),
        ('public.audit_logs'::regclass, 'user_id'),
        ('public.medication_orders'::regclass, 'prescriber_id'),
        ('public.medication_administrations'::regclass, 'administered_by'),
        ('public.medical_records'::regclass, 'clinician_id')
      )
  loop
    execute format('alter table %s drop constraint %I', r.tbl, r.conname);
  end loop;
end
$$;

-- 2. Convert the columns to bigint ------------------------------------------
alter table public.scan_logs
  alter column user_id type bigint using null;

alter table public.audit_logs
  alter column user_id type bigint using null;

alter table public.medication_orders
  alter column prescriber_id type bigint using null;

alter table public.medication_administrations
  alter column administered_by type bigint using null;

alter table public.medical_records
  alter column clinician_id type bigint using null;

-- 3. Re-create the foreign keys against public.users ------------------------
alter table public.scan_logs
  add constraint scan_logs_user_id_fkey
  foreign key (user_id) references public.users(id) on delete set null;

alter table public.audit_logs
  add constraint audit_logs_user_id_fkey
  foreign key (user_id) references public.users(id) on delete set null;

alter table public.medication_orders
  add constraint medication_orders_prescriber_id_fkey
  foreign key (prescriber_id) references public.users(id) on delete set null;

alter table public.medication_administrations
  add constraint medication_administrations_administered_by_fkey
  foreign key (administered_by) references public.users(id) on delete set null;

alter table public.medical_records
  add constraint medical_records_clinician_id_fkey
  foreign key (clinician_id) references public.users(id) on delete set null;

-- 4. Ask PostgREST to refresh its schema cache ------------------------------
notify pgrst, 'reload schema';
