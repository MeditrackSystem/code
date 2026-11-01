-- Seed data (run after schema.sql).
insert into public.users (employee_id, name, username, password, role, status) values
 ('U001','System Administrator','admin','admin123','Administrator','Active'),
 ('U002','Dr. Maria Santos','maria.santos','password','Doctor','Active'),
 ('U003','Dr. John Lee','john.lee','password','Doctor','Active'),
 ('U004','Nurse Joy Reyes','nurse.joy','password','Nurse','Active'),
 ('U005','Nurse Anna Cruz','anna.cruz','password','Nurse','Active'),
 ('U006','Pharmacist Leo Tan','leo.tan','password','Pharmacist','Active'),
 ('U007','Read-Only Staff','staff.readonly','password','Read-only staff','Active')
on conflict (username) do nothing;

insert into public.patients (patient_code, name, birth_date, room, bed, attending_physician, admission_status) values
 ('PAT-2026-001','Juan Dela Cruz','1985-05-12','201','A','Dr. Maria Santos','Admitted'),
 ('PAT-2026-002','Maria Clara Reyes','1990-09-22','202','B','Dr. John Lee','Admitted'),
 ('PAT-2026-003','Pedro Santos','1978-03-14','203','A','Dr. Maria Santos','Admitted'),
 ('PAT-2026-004','Ana Lim','2001-11-30','204','C','Dr. John Lee','Outpatient'),
 ('PAT-2026-005','Roberto Garcia','1965-07-08','205','B','Dr. Maria Santos','Admitted')
on conflict (patient_code) do nothing;

insert into public.rfid_tags (tag_token, patient_id, status, assigned_at) values
 ('2066071338', (select id from patients where patient_code='PAT-2026-001'), 'Active', now()),
 ('2066071339', (select id from patients where patient_code='PAT-2026-002'), 'Active', now()),
 ('2066071340', (select id from patients where patient_code='PAT-2026-003'), 'Active', now()),
 ('2066071341', (select id from patients where patient_code='PAT-2026-004'), 'Active', now()),
 ('2066071342', (select id from patients where patient_code='PAT-2026-005'), 'Active', now())
on conflict (tag_token) do nothing;

insert into public.medication_orders (patient_id, medication, dose, route, frequency, status) values
 ((select id from patients where patient_code='PAT-2026-001'),'Paracetamol','500mg','Oral','Every 8 hours','Active'),
 ((select id from patients where patient_code='PAT-2026-001'),'Amoxicillin','250mg','Oral','Every 6 hours','Active'),
 ((select id from patients where patient_code='PAT-2026-002'),'Ibuprofen','200mg','Oral','Every 8 hours','Active');
