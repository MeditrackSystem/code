// Seeds realistic demo activity (scan logs, audit trail, medication
// administrations) so the dashboard and log pages are not empty.
//
// Usage:  node supabase/seed_demo_activity.mjs
// Reads VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY from web/.env
//
// Note: if the remote schema still has UUID staff columns (left over from an
// older Supabase Auth setup), staff references are written as null. Run
// supabase/fix_schema.sql once to convert them to bigint and re-run this seed.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const env = fs.readFileSync(path.join(here, '..', 'web', '.env'), 'utf8')
const URL_BASE = /VITE_SUPABASE_URL=(.*)/.exec(env)[1].trim()
const KEY = /VITE_SUPABASE_ANON_KEY=(.*)/.exec(env)[1].trim()

const headers = {
  apikey: KEY,
  Authorization: `Bearer ${KEY}`,
  'Content-Type': 'application/json',
}

async function get(table) {
  const res = await fetch(`${URL_BASE}/rest/v1/${table}?select=*`, { headers })
  return res.json()
}

async function clear(table) {
  const res = await fetch(`${URL_BASE}/rest/v1/${table}?id=not.is.null`, { method: 'DELETE', headers })
  if (!res.ok && res.status !== 404) console.log(`  ${table}: clear failed ${res.status}`)
}

async function insert(table, rows, { uuidColumns = [] } = {}) {
  if (!rows.length) return
  const send = async (payload) => fetch(`${URL_BASE}/rest/v1/${table}`, {
    method: 'POST',
    headers: { ...headers, Prefer: 'return=minimal' },
    body: JSON.stringify(payload),
  })

  let res = await send(rows)
  if (!res.ok) {
    const body = await res.text()
    if (res.status === 400 && /uuid/.test(body) && uuidColumns.length) {
      const cleaned = rows.map((row) => {
        const copy = { ...row }
        uuidColumns.forEach((c) => { copy[c] = null })
        return copy
      })
      res = await send(cleaned)
      if (res.ok) {
        console.log(`  ${table}: +${rows.length} rows (staff references skipped — UUID columns still in place)`)
        return
      }
    }
    throw new Error(`${table}: ${res.status} ${body}`)
  }
  console.log(`  ${table}: +${rows.length} rows`)
}

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)]
const hoursAgo = (h) => new Date(Date.now() - h * 3600 * 1000).toISOString()

const [users, patients, tags, orders] = await Promise.all([
  get('users'),
  get('patients'),
  get('rfid_tags'),
  get('medication_orders'),
])

const inOrders = new Set(orders.map((o) => o.id))
const cleanOrders = orders.filter((o) => inOrders.has(o.id) && !/^TestOnly/.test(o.medication))
const staff = users.filter((u) => u.status === 'Active')
const nurses = staff.filter((u) => u.role === 'Nurse')
const doctors = staff.filter((u) => u.role === 'Doctor')
const activeTags = tags.filter((t) => t.status === 'Active')

console.log('Clearing old demo activity…')
await clear('scan_logs')
await clear('audit_logs')
await clear('medication_administrations')
await clear('medical_records')
for (const order of orders.filter((o) => /^TestOnly/.test(o.medication))) {
  await fetch(`${URL_BASE}/rest/v1/medication_orders?id=eq.${order.id}`, { method: 'DELETE', headers })
}

// The original CSV seed was imported more than once — drop duplicate orders.
const seenOrders = new Map()
for (const order of orders.filter((o) => !/^TestOnly/.test(o.medication))) {
  const key = `${order.patient_id}|${order.medication}|${order.dose}`
  if (seenOrders.has(key)) {
    await fetch(`${URL_BASE}/rest/v1/medication_orders?id=eq.${order.id}`, { method: 'DELETE', headers })
  } else {
    seenOrders.set(key, order.id)
  }
}
const keptOrders = [...seenOrders.values()]

// Every patient should have a couple of active medication orders.
const patientsWithOrders = new Set(keptOrders.map((id) => orders.find((o) => o.id === id).patient_id))
const formulary = [
  { medication: 'Paracetamol', dose: '500mg', route: 'Oral', frequency: 'Every 8 hours' },
  { medication: 'Amoxicillin', dose: '500mg', route: 'Oral', frequency: 'Every 12 hours' },
]
const extraOrders = []
for (const patient of patients) {
  if (patientsWithOrders.has(patient.id)) continue
  for (const med of formulary) {
    extraOrders.push({ ...med, patient_id: patient.id, status: 'Active' })
  }
}
if (extraOrders.length) await insert('medication_orders', extraOrders)

const activeOrders = (await get('medication_orders')).filter((o) => !/^TestOnly/.test(o.medication))

// ---------- clinical records ----------
const noteTemplates = [
  ['Diagnosis', 'Community-acquired pneumonia. Started on antibiotics; monitor temperature every 4 hours.'],
  ['Note', 'Patient reports reduced pain after morning dose. Ambulating without assistance.'],
  ['Allergy', 'Penicillin — mild rash. Avoid beta-lactam antibiotics.'],
  ['History', 'Hypertension managed with lifestyle changes. No previous surgeries.'],
]
const recordRows = []
patients.forEach((patient, index) => {
  const count = 2 + (index % 2)
  for (let i = 0; i < count; i++) {
    const [record_type, note] = noteTemplates[(index + i) % noteTemplates.length]
    recordRows.push({
      patient_id: patient.id,
      clinician_id: pick(doctors.length ? doctors : staff).id,
      record_type,
      note,
      recorded_at: hoursAgo(4 + i * 14 + index * 3),
    })
  }
})
await insert('medical_records', recordRows, { uuidColumns: ['clinician_id'] })

// ---------- scan logs (last 7 days, busier during day shift) ----------
const readers = ['Keyboard Wedge', 'USB Reader', 'RC522 Module']
const scans = []
for (let day = 6; day >= 0; day--) {
  const count = 9 + Math.floor(Math.random() * 8) + (day < 3 ? 5 : 0)
  for (let i = 0; i < count; i++) {
    const hour = 7 + Math.floor(Math.random() * 12) + day * 24
    const failed = Math.random() < 0.07
    scans.push({
      tag_id: failed ? null : pick(activeTags).id,
      user_id: pick(staff).id,
      reader_type: pick(readers),
      scanned_at: hoursAgo(hour + Math.random()),
      outcome: failed ? 'Unknown tag' : 'Success',
    })
  }
}
await insert('scan_logs', scans, { uuidColumns: ['user_id'] })

// ---------- audit trail ----------
const actions = [
  ['LOGIN', 'session'],
  ['VIEW_PATIENT', 'patients'],
  ['SCAN_RFID', 'rfid_tags'],
  ['ADD_MEDICATION', 'medication_orders'],
  ['UPDATE_PATIENT', 'patients'],
  ['ADMINISTER_MEDICATION', 'medication_administrations'],
  ['CREATE_USER', 'users'],
]
const audits = []
for (let i = 0; i < 46; i++) {
  const [action, record] = pick(actions)
  const patient = pick(patients)
  audits.push({
    user_id: pick(staff).id,
    action,
    record_type: record,
    record_id: record === 'patients' ? String(patient.id) : '',
    occurred_at: hoursAgo(Math.random() * 72),
  })
}
await insert('audit_logs', audits, { uuidColumns: ['user_id'] })

// ---------- medication administrations ----------
const adminRows = []
for (const order of activeOrders) {
  for (let step = 0; step < 3; step++) {
    const when = 3 + step * 7 + Math.random() * 2
    const missed = Math.random() < 0.1
    adminRows.push({
      order_id: order.id,
      scheduled_at: hoursAgo(when),
      administered_at: missed ? null : hoursAgo(when - 0.3),
      status: missed ? 'Missed' : 'Given',
      administered_by: missed ? null : pick(nurses).id,
      notes: missed ? 'Patient unavailable at scheduled time' : '',
    })
  }
}
for (const order of activeOrders.slice(0, 4)) {
  adminRows.push({
    order_id: order.id,
    scheduled_at: new Date(Date.now() + 2 * 3600 * 1000).toISOString(),
    administered_at: null,
    status: 'Pending',
    administered_by: null,
    notes: '',
  })
}
await insert('medication_administrations', adminRows, { uuidColumns: ['administered_by'] })

console.log('Done.')
