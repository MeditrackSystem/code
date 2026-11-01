# MediTrack — Supabase Website + Raspberry Pi Sync

A prototype hospital patient-monitoring system: RFID wristbands are scanned on a
Raspberry Pi, records live in Supabase, and staff use the web app to review
patients, medications, scans and audit history.

- `web/` — React + Vite website (Supabase client, no Supabase Auth)
- `supabase/` — SQL schema, RLS, seed, schema repair, demo activity seed
- `rpi_supabase.py` — Raspberry Pi PyQt5 app (CSV cache + Supabase sync)
- `database/*.csv` — local offline cache on the RPI

## Login model

There is **no Supabase Auth / email flow**. Accounts live in a plain
`public.users` table:

- The website checks `username` + `password` + `status = 'Active'`.
- The admin signs in with `admin` / `admin123` and creates staff accounts from
  **User Management**.
- The admin hands each user their username and password directly.

## 1. Supabase setup

1. Create a Supabase project.
2. SQL editor → run `supabase/schema.sql`.
3. SQL editor → run `supabase/rls.sql` (Row Level Security is disabled for this
   prototype so the anon key can read and write).
4. SQL editor → run `supabase/seed.sql` (default admin + patient data).
5. **If the project previously used Supabase Auth**, run
   `supabase/fix_schema.sql` once. It converts the leftover `uuid` staff columns
   (`scan_logs.user_id`, `audit_logs.user_id`, `medication_orders.prescriber_id`,
   `medication_administrations.administered_by`, `medical_records.clinician_id`)
   to `bigint` references on `public.users`. Without it, joins like
   `scan_logs → users` fail and staff attribution is dropped.
6. Optional — fill the dashboard with demo activity:
   ```
   node supabase/seed_demo_activity.mjs
   ```
   This creates ~100 scans across the last 7 days, an audit trail and medication
   administrations. Run it again any time to refresh the demo data.

## 2. Website

```
cd web
npm install
# .env contains VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY
npm run dev
```

Build for production with `npm run build`.

Pages: Dashboard, Patients, Patient Record, RFID Tags, Scan Logs, Audit Logs and
User Management (administrators only).

## 3. Raspberry Pi

```
pip install PyQt5 bleak requests
python rpi_supabase.py
```

Optional environment variables:

```
SUPABASE_URL=https://kjadezwzwvfualbvjrkm.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service role key>   # recommended for writes
SUPABASE_SYNC_INTERVAL=60
```

Without a service role key the Pi uses the anon key, which is enough to insert
scan and audit logs.

## Data flow

1. The Pi reads an RFID wristband (keyboard wedge, USB reader or RC522).
2. It looks up the patient bundle from the local CSV cache, so scanning still
   works offline.
3. Scans and audit events are appended to CSV and pushed to Supabase in the
   background.
4. The website reads Supabase directly and writes patient, tag, medication and
   clinical-record updates back to it.
