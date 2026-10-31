# PROPOSED SYSTEM WORKFLOW AND FUNCTIONAL DESIGN

*Integrated Digital Medical Record and Medication Monitoring Management with RFID Application*

Raspberry Pi • Python • Wired and Bluetooth RFID Readers

Design proposal based on the uploaded research manuscript. The hardware/software implementation details below are recommendations, not claims that the system is already implemented.

# 1. System Overview

The proposed system uses RFID wristbands to link patients to secure electronic records. A wired or Bluetooth RFID reader captures the wristband identifier and sends it to a Python program running on a Raspberry Pi. The program validates the logged-in healthcare worker’s permissions, retrieves the matching patient record, and displays the relevant patient and medication details. Authorized personnel can update clinical documentation and medication administration status, while the system preserves a dated activity log.

## System Process Flow

1. Administrator creates staff accounts and registers a patient.
2. An unassigned RFID wristband is scanned and linked to the patient’s unique database record.
3. A healthcare worker signs in using an authorized account.
4. The patient wristband is scanned using either a wired or a compatible Bluetooth RFID reader.
5. Python checks the RFID identifier and the healthcare worker’s access permission.
6. The patient profile, medical record summary, and prescribed medications are displayed.
7. Authorized users document medication administration and other permitted updates.
8. The system saves time-stamped updates and audit logs.

# 2. User Registration and Access

## A. Register Hospital Personnel

| Field | Suggested input |
| --- | --- |
| Employee ID | Auto-generated / institution-issued |
| Full name | First and last name |
| Role | Administrator, doctor, nurse, authorized read-only staff |
| Department / ward | Assigned service area |
| Username / email | Unique login identifier |
| Password | Stored only as a secure password hash |
| Account status | Active / inactive |

| Role | Recommended permission |
| --- | --- |
| Administrator | Manage users, patient registration, RFID assignments, device settings and audit access |
| Doctor | Review authorized patient records, enter diagnoses and prescriptions |
| Nurse | View assigned patient records and document medication administration |
| Read-only staff | View approved limited information; no clinical editing |

All workers should log in before scanning RFID wristbands. Role-based access must restrict which medical information each user may view or edit.

## B. Register Patients

| Category | Fields |
| --- | --- |
| Patient identity | Patient ID, full name, birth date, sex, contact information |
| Hospital information | Admission date, admission status, room, bed, attending physician |
| Medical record | Diagnoses, medical history, known allergies, clinical notes |
| Emergency contact | Name, relationship, phone number |
| RFID assignment | RFID wristband identifier, activation status, assignment date |

Recommended registration sequence: save the new patient record; scan a wristband; confirm the wristband is not assigned elsewhere; associate its identifier with the new patient; and test a retrieval scan. Replace or deactivate a lost wristband without deleting the patient record.

# 3. RFID Reader Operation

| Reader | Proposed use | Connection |
| --- | --- | --- |
| Wired RFID reader | Registration or stationary hospital workstation | USB HID, USB serial, or compatible GPIO interface to Raspberry Pi |
| Bluetooth RFID reader | Portable patient-room scanning | Bluetooth HID, serial, or a documented BLE interface to Raspberry Pi or supported client |

Both readers should read wristbands using the same compatible RFID frequency/protocol. Model-specific Linux drivers and data formats must be confirmed before implementation. A Bluetooth-enabled device is not necessarily an RFID reader.

## What happens after an RFID scan?

- Reader captures the tag identifier (UID or reader-provided token).
- Python receives and normalizes the scan.
- The system looks up the assigned patient record.
- The signed-in user’s authorization is checked before revealing clinical information.
- The system displays the relevant patient view or an error message: unknown tag, inactive tag, no authorization, or reader disconnected.
- The scan event is saved with user, reader, date/time, and outcome.

# 4. Patient Information Display After Scanning

The first screen should show a short and clear patient summary, with links or tabs to restricted detailed sections.

| Screen section | Displayed information |
| --- | --- |
| Identification | Patient name, unique patient ID, patient photograph if available, admission status |
| Location / care team | Room, bed, attending physician, admission date |
| Safety summary | Known allergies and important clinician-recorded warnings |
| Medication summary | Medication name, prescribed dose, route, due time, status |
| Medical record | Diagnoses, history, treatment notes (permission-controlled) |
| Actions | Open full record, view medication log, record administration, view history |

## Illustrative scan result (fictional data)

| Field | Example |
| --- | --- |
| Patient | Juan Dela Cruz |
| Patient ID | PAT-2026-001 |
| Room / bed | 201 / A |
| Attending physician | Dr. Maria Santos |
| RFID status | Assigned and active |
| Medication A | 8:00 AM — Recorded |
| Medication B | 2:00 PM — Pending |

The patient must still be identified according to the facility’s clinical policy; an RFID wristband scan alone is not a sufficient safety check for medication administration.

# 5. Medication Monitoring and Administration

The medication module should maintain the physician-authorized prescription and separate records for each scheduled/actual administration event.

| Data field | Purpose |
| --- | --- |
| Medication order | Drug name, dose, route, frequency, prescribing physician |
| Schedule | Due date/time, order start/end dates where applicable |
| Administration status | Pending, Given, Missed, Held, Refused |
| Actual administration | Date/time and staff member completing the record |
| Notes | Reason for missed/held/refused dose, remarks and corrections |
| Audit trail | Who created, changed or confirmed the record and when |

Suggested workflow: after scanning and confirming patient identity using at least two approved identifiers, the nurse reviews the medication order and due schedule, verifies required medication checks, administers the medication as clinically ordered, and only then documents the actual outcome. Scanning should never automatically mark a dose as administered. Completed entries stay in administration history instead of being deleted.

# 6. Recommended Software and System Modules

| Component | Recommendation |
| --- | --- |
| Computer / OS | Raspberry Pi 4 or 5; Raspberry Pi OS |
| Programming language | Python |
| Web backend | Flask |
| User interface | HTML, CSS, JavaScript and Bootstrap |
| Database | SQLite for an offline research prototype; PostgreSQL for multiuser scaling |
| Reader integration | USB HID/serial/GPIO and model-supported Bluetooth interface |
| Security | Session login, hashed passwords, permission checks, backups and activity logs |

| Module | Functions |
| --- | --- |
| Dashboard | Patient counts, medications due, recent activity |
| User management | Manage healthcare worker accounts and roles |
| Patient management | Register, search and update patient information |
| RFID management | Assign, replace, disable and test wristbands |
| Medical records | View and update permitted clinical records |
| Medication monitoring | View prescriptions, due items and administration history |
| Scan history | Time, operator, reader used, and scan outcome |
| Reports / settings | Generate authorized reports, configure devices and backups |

# 7. Suggested Database Tables

| Table | Core fields |
| --- | --- |
| users | id, employee_id, name, username, password_hash, role, status |
| patients | id, patient_code, name, birth_date, room, bed, attending_physician, admission_status |
| rfid_tags | id, tag_token, patient_id, status, assigned_at, deactivated_at |
| medical_records | id, patient_id, clinician_id, record_type, note, recorded_at |
| medication_orders | id, patient_id, medication, dose, route, frequency, prescriber_id, status |
| medication_administrations | id, order_id, scheduled_at, administered_at, status, administered_by, notes |
| scan_logs | id, tag_id, user_id, reader_type, scanned_at, outcome |
| audit_logs | id, user_id, action, record_type, record_id, occurred_at |

# 8. Security, Scope and Practical Limitations

- Store only an opaque identifier on the RFID wristband; keep patient health records in the protected database.
- Do not use an RFID UID alone to authenticate medical staff or authorize record changes.
- Protect sensitive medical information through authenticated access, role-based permissions, secure communications, backups and access logging.
- A basic RFID scan shows that a wristband was read at a particular reader; it does not establish continuous real-time patient location.
- The Bluetooth reader must be checked for actual RFID support, compatible tag technology and reliable Raspberry Pi communication.
- The system supports record retrieval and medication documentation but does not make diagnoses or clinical decisions.
- For school testing, use synthetic patient data and simulated medication events unless authorized clinical and privacy arrangements are in place.

# 9. Recommended Development Sequence

Phase 1 — Develop the staff login and permissions.

Phase 2 — Develop patient registration and the local database.

Phase 3 — Connect and validate the wired RFID reader.

Phase 4 — Implement wristband assignment and patient retrieval.

Phase 5 — Build medical record and medication administration modules.

Phase 6 — Integrate the Bluetooth reader and test connection recovery.

Phase 7 — Test access restrictions, error handling, activity logs, backups and usability.

The proposed functionality aligns with the research manuscript’s objectives of patient identification, digital medical record access, medication monitoring, and evaluation of usability and reliability. Final hardware connections, RFID protocols, clinical validation, and deployment permissions depend on the selected reader models and testing environment.
