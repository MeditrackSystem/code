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

  async function load() {
    setLoading(true)
    try {
      const { data: p } = await supabase.from('patients').select('*').eq('id', id).single()
      setPatient(p)
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
    const optimistic = { id: `tmp-${Date.now()}`, order_id: orderId, status, administered_at: new Date().toISOString(), administered_by: user?.id }
    setAdmins(prev => [...prev, optimistic])
    setSaving(true)
    try {
      const { error } = await insertTolerant('medication_administrations', {
        order_id: orderId, scheduled_at: new Date().toISOString(), administered_at: new Date().toISOString(), status, administered_by: user?.id, notes: ''
      }, ['administered_by'])
      if (error) { setMsg(error.message); await load(); return }
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

      <div className="card" style={{ marginTop: 16 }}>
        <h3 className="card-title">Clinical Timeline</h3>
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
