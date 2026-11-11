import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { supabase } from '../supabaseClient'
import { getSession } from '../session'
import { insertTolerant } from '../db'
import { formatDate, formatDateTime, initials } from '../utils'
import Icon from '../components/Icon'

export default function PatientDetail() {
  const { id } = useParams()
  const [patient, setPatient] = useState(null)
  const [tags, setTags] = useState([])
  const [orders, setOrders] = useState([])
  const [records, setRecords] = useState([])
  const [admins, setAdmins] = useState([])
  const [newTag, setNewTag] = useState('')
  const [medForm, setMedForm] = useState({ medication: '', dose: '', route: 'Oral', frequency: '' })
  const [recForm, setRecForm] = useState({ record_type: 'Note', note: '' })
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [editOpen, setEditOpen] = useState(false)
  const [editForm, setEditForm] = useState({ name: '', birth_date: '', room: '', bed: '', attending_physician: '', admission_status: 'Admitted' })
  const [doctors, setDoctors] = useState([])

  async function load() {
    setLoading(true)
    try {
      const { data: p } = await supabase.from('patients').select('*').eq('id', id).single()
      setPatient(p)
      if (p) setEditForm({ name: p.name || '', birth_date: p.birth_date || '', room: p.room || '', bed: p.bed || '', attending_physician: p.attending_physician || '', admission_status: p.admission_status || 'Admitted' })
      const { data: u } = await supabase.from('users').select('name, role').eq('status', 'Active')
      setDoctors((u || []).filter(x => /doctor|physician/i.test(x.role || '')))
      const { data: t } = await supabase.from('rfid_tags').select('*').eq('patient_id', id)
      setTags(t || [])
      const { data: o } = await supabase.from('medication_orders').select('*').eq('patient_id', id)
      setOrders(o || [])
      const { data: r } = await supabase.from('medical_records').select('*').eq('patient_id', id).order('recorded_at', { ascending: false })
      setRecords(r || [])
      const ids = (o || []).map(x => x.id)
      if (ids.length) {
        const { data: a } = await supabase.from('medication_administrations').select('*').in('order_id', ids)
        setAdmins(a || [])
      } else setAdmins([])
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [id])

  async function assignTag(e) {
    e.preventDefault()
    if (!newTag.trim()) return
    setSaving(true)
    try {
      const { error } = await supabase.from('rfid_tags').insert({ tag_token: newTag.trim(), patient_id: id, status: 'Active', assigned_at: new Date().toISOString() })
      if (error) { setMsg(error.message); return }
      setNewTag('')
      await load()
    } finally {
      setSaving(false)
    }
  }

  async function addMed(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const { error } = await supabase.from('medication_orders').insert({ ...medForm, patient_id: id, status: 'Active' })
      if (error) { setMsg(error.message); return }
      setMedForm({ medication: '', dose: '', route: 'Oral', frequency: '' })
      await load()
    } finally {
      setSaving(false)
    }
  }

  async function addRec(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const user = getSession()
      const { error } = await insertTolerant('medical_records', { ...recForm, patient_id: id, clinician_id: user.id, recorded_at: new Date().toISOString() }, ['clinician_id'])
      if (error) { setMsg(error.message); return }
      setRecForm({ record_type: 'Note', note: '' })
      setMsg('')
      await load()
    } finally {
      setSaving(false)
    }
  }

  async function recordAdmin(orderId, status) {
    const user = getSession()
    const now = new Date().toISOString()
    const latest = admins.filter(a => a.order_id === orderId).slice(-1)[0]
    // Optimistic update of the current status
    if (latest) {
      setAdmins(prev => prev.map(a => a.id === latest.id ? { ...a, status, administered_at: now } : a))
    } else {
      setAdmins(prev => [...prev, { id: `tmp-${Date.now()}`, order_id: orderId, status, administered_at: now, administered_by: user?.id }])
    }
    setSaving(true)
    try {
      let error
      if (latest && !String(latest.id).startsWith('tmp-')) {
        const res = await supabase.from('medication_administrations').update({
          status, administered_at: now, administered_by: user?.id
        }).eq('id', latest.id)
        error = res.error
      } else {
        const res = await insertTolerant('medication_administrations', {
          order_id: orderId, scheduled_at: now, administered_at: now, status, administered_by: user?.id, notes: ''
        }, ['administered_by'])
        error = res.error
      }
      if (error) { setMsg(error.message); await load(); return }
      setMsg('')
      await load()
    } finally {
      setSaving(false)
    }
  }

  async function savePatient(e) {
    if (e && e.preventDefault) e.preventDefault()
    setSaving(true)
    try {
      const { error } = await supabase.from('patients').update(editForm).eq('id', id)
      if (error) { setMsg(error.message); return }
      setEditOpen(false)
      setMsg('')
      await load()
    } finally {
      setSaving(false)
    }
  }

  if (!patient) return <div className="card"><div className="empty">Loading patient…</div></div>

  const activeTag = tags.find(t => t.status === 'Active')
  const given = admins.filter(a => a.status === 'Given').length

  return (
    <div>
      <div className="page-header">
        <div>
          <Link to="/patients" className="muted" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <Icon name="arrowLeft" size={14} /> Back to Patients
          </Link>
          <h1 className="page-title" style={{ marginTop: 6 }}>{patient.name}</h1>
          <p className="page-subtitle mono">{patient.patient_code}</p>
        </div>
        <span className={'badge ' + (patient.admission_status === 'Admitted' ? 'badge-blue' : patient.admission_status === 'Outpatient' ? 'badge-amber' : 'badge-gray')}>{patient.admission_status}</span>
        <button className="btn btn-primary btn-sm" onClick={() => setEditOpen(true)}>Edit Patient</button>
      </div>

      {msg && <div className="alert alert-error">{msg}</div>}

      <div className="card">
        <div className="patient-hero">
          <div className="patient-avatar">{initials(patient.name)}</div>
          <div style={{ flex: 1, minWidth: 220 }}>
            <div className="detail-label">Patient record</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--ink)', letterSpacing: '-.02em', marginTop: 2 }}>{patient.name}</div>
            <div className="row" style={{ marginTop: 8 }}>
              <span className="badge badge-blue">{patient.patient_code}</span>
              <span className={'badge ' + (activeTag ? 'badge-green' : 'badge-gray')}>{activeTag ? 'RFID active' : 'No RFID tag'}</span>
              <span className="badge badge-gray">{orders.length} medication{orders.length === 1 ? '' : 's'}</span>
            </div>
          </div>
          <div className="detail-grid" style={{ flex: 2, minWidth: 280 }}>
            <div className="detail-item"><div className="detail-label">Room / Bed</div><div className="detail-value">{patient.room || '—'} / {patient.bed || '—'}</div></div>
            <div className="detail-item"><div className="detail-label">Attending Physician</div><div className="detail-value">{patient.attending_physician || '—'}</div></div>
            <div className="detail-item"><div className="detail-label">Birth Date</div><div className="detail-value">{formatDate(patient.birth_date)}</div></div>
            <div className="detail-item"><div className="detail-label">Doses Given</div><div className="detail-value">{given}</div></div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3 className="card-title">Clinical Record</h3>
        <p className="card-sub">Recorded notes and diagnoses.</p>
        {records.length === 0 && (
          <div className="empty-state">
            <span className="ico"><Icon name="file" size={20} /></span>
            <b>No clinical records</b>
            <span>Notes, diagnoses and allergies will appear here in reverse-chronological order.</span>
          </div>
        )}
        <div className="timeline" style={{ marginTop: 8 }}>
          {records.map(r => (
            <div key={r.id} className="timeline-item">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="badge badge-blue">{r.record_type}</span>
                <span className="muted">{formatDateTime(r.recorded_at)}</span>
              </div>
              <p style={{ margin: '10px 0 0', color: 'var(--text)' }}>{r.note}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h3 className="card-title">RFID Wristband</h3>
          <p className="card-sub">Assign a tag token to this patient.</p>
          <form onSubmit={assignTag} className="row" style={{ marginBottom: 14 }}>
            <input className="input" style={{ flex: 1 }} placeholder="Tag token e.g. 2066071338" value={newTag} onChange={e => setNewTag(e.target.value)} />
            <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Assign'}</button>
          </form>
          <div className="stack">
            {tags.length === 0 && <div className="muted">No RFID wristband assigned yet. Enter a tag token above.</div>}
            {tags.map(t => (
              <div key={t.id} className="row" style={{ justifyContent: 'space-between', border: '1px solid var(--line)', borderRadius: 10, padding: '11px 14px' }}>
                <span className="mono">{t.tag_token}</span>
                <span className={'badge ' + (t.status === 'Active' ? 'badge-green' : 'badge-gray')}>{t.status}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">Add Clinical Record</h3>
          <p className="card-sub">Notes, diagnosis, allergy, or history.</p>
          <form onSubmit={addRec} className="stack">
            <select className="select" value={recForm.record_type} onChange={e => setRecForm({ ...recForm, record_type: e.target.value })}>
              <option>Note</option><option>Diagnosis</option><option>Allergy</option><option>History</option>
            </select>
            <input className="input" placeholder="Write a clinical note…" value={recForm.note} onChange={e => setRecForm({ ...recForm, note: e.target.value })} required />
            <button className="btn btn-success" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Add Record'}</button>
          </form>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <div>
            <h3 className="card-title">Medications</h3>
            <p className="card-sub" style={{ marginBottom: 0 }}>Prescribed medication orders and administration status.</p>
          </div>
          <span className="badge badge-blue">{orders.length} orders</span>
        </div>
        <form onSubmit={addMed} className="form-grid" style={{ margin: '16px 0 18px' }}>
          <div className="field"><label>Medication</label><input className="input" value={medForm.medication} onChange={e => setMedForm({ ...medForm, medication: e.target.value })} required placeholder="Paracetamol" /></div>
          <div className="field"><label>Dose</label><input className="input" value={medForm.dose} onChange={e => setMedForm({ ...medForm, dose: e.target.value })} placeholder="500mg" /></div>
          <div className="field"><label>Route</label>
            <select className="select" value={medForm.route} onChange={e => setMedForm({ ...medForm, route: e.target.value })}>
              <option>Oral</option><option>IV</option><option>IM</option><option>Topical</option>
            </select>
          </div>
          <div className="field"><label>Frequency</label><input className="input" value={medForm.frequency} onChange={e => setMedForm({ ...medForm, frequency: e.target.value })} placeholder="Every 8 hours" /></div>
          <div className="field" style={{ justifyContent: 'flex-end' }}><button className="btn btn-primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Add Order'}</button></div>
        </form>

        {orders.length === 0 && (
          <div className="empty-state">
            <span className="ico"><Icon name="pill" size={20} /></span>
            <b>No medication orders</b>
            <span>Add the first order above to start tracking administration.</span>
          </div>
        )}
        {orders.map(o => {
          const latest = admins.filter(a => a.order_id === o.id).slice(-1)[0]
          const status = latest ? latest.status : 'Pending'
          const badge = status === 'Given' ? 'badge-green' : status === 'Pending' ? 'badge-amber' : 'badge-red'
          return (
            <div key={o.id} className="med-item">
              <div className="med-head">
                <div>
                  <div className="med-name">{o.medication}</div>
                  <div className="muted">{o.dose} · {o.route} · {o.frequency}</div>
                </div>
                <span className={'badge ' + badge}>{status}</span>
              </div>
              <div className="row" style={{ marginTop: 12 }}>
                {['Given', 'Missed', 'Held', 'Refused'].map(s => (
                  <button key={s} className="btn btn-ghost btn-sm" disabled={saving} onClick={() => recordAdmin(o.id, s)}>{saving ? '…' : s}</button>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    {editOpen && (
      <div className="modal-backdrop" onClick={() => setEditOpen(false)}>
        <div className="modal" onClick={e => e.stopPropagation()}>
          <div className="modal-head">
            <div>
              <h3>Edit Patient</h3>
              <p>Update room, bed, physician and status.</p>
            </div>
            <button className="modal-close" onClick={() => setEditOpen(false)} aria-label="Close"><Icon name="x" size={16} /></button>
          </div>
          <form onSubmit={savePatient} className="modal-body">
            <div className="form-grid">
              <div className="field"><label>Name</label><input className="input" value={editForm.name} onChange={e => setEditForm({ ...editForm, name: e.target.value })} required /></div>
              <div className="field"><label>Birth Date</label><input className="input" type="date" value={editForm.birth_date} onChange={e => setEditForm({ ...editForm, birth_date: e.target.value })} /></div>
              <div className="field"><label>Room</label><input className="input" value={editForm.room} onChange={e => setEditForm({ ...editForm, room: e.target.value })} /></div>
              <div className="field"><label>Bed</label><input className="input" value={editForm.bed} onChange={e => setEditForm({ ...editForm, bed: e.target.value })} /></div>
              <div className="field"><label>Attending Physician</label>
                <select className="select" value={editForm.attending_physician} onChange={e => setEditForm({ ...editForm, attending_physician: e.target.value })}>
                  {doctors.map(d => <option key={d.name} value={d.name}>{d.name}</option>)}
                </select>
              </div>
              <div className="field"><label>Admission Status</label>
                <select className="select" value={editForm.admission_status} onChange={e => setEditForm({ ...editForm, admission_status: e.target.value })}>
                  <option>Admitted</option><option>Outpatient</option><option>Discharged</option>
                </select>
              </div>
            </div>
            {msg && <div className="alert alert-error" style={{ marginTop: 14 }}>{msg}</div>}
          </form>
          <div className="modal-foot">
            <button type="button" className="btn btn-ghost" onClick={() => setEditOpen(false)}>Cancel</button>
            <button type="submit" className="btn btn-success" onClick={savePatient} disabled={saving}>{saving ? 'Saving…' : 'Save Changes'}</button>
          </div>
        </div>
      </div>
    )}
    {(loading || saving) && (
      <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
        <div style={{ background: 'white', padding: '24px 32px', borderRadius: 12, boxShadow: '0 10px 30px rgba(0,0,0,0.2)', textAlign: 'center' }}>
          <div style={{ width: 36, height: 36, border: '4px solid #e2e8f0', borderTopColor: '#2563eb', borderRadius: '50%', margin: '0 auto 12px', animation: 'spin 0.8s linear infinite' }} />
          <div style={{ fontWeight: 600, color: '#1e293b' }}>{saving ? 'Saving…' : 'Loading…'}</div>
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    )}
    </div>
  )
}
