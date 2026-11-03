import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../supabaseClient'
import { initials } from '../utils'
import Icon from '../components/Icon'

export default function Patients() {
  const [patients, setPatients] = useState([])
  const [doctors, setDoctors] = useState([])
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('All')
  const [form, setForm] = useState({ patient_code: '', name: '', birth_date: '', room: '', bed: '', attending_physician: '', admission_status: 'Admitted', rfid_tag: '' })
  const [show, setShow] = useState(false)
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const [{ data: p }, { data: u }] = await Promise.all([
        supabase.from('patients').select('*').order('id'),
        supabase.from('users').select('name, role').eq('status', 'Active'),
      ])
      setPatients(p || [])
      setDoctors((u || []).filter(x => /doctor|physician/i.test(x.role || '')))
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  async function remove(id) {
    if (!confirm('Delete this patient?')) return
    setMsg('')
    const { error: tagErr } = await supabase.from('rfid_tags').delete().eq('patient_id', id)
    if (tagErr) { setMsg(tagErr.message); }
    const { error } = await supabase.from('patients').delete().eq('id', id)
    if (error) { setMsg(error.message); return }
    await load()
  }

  async function add(e) {
    if (e && e.preventDefault) e.preventDefault()
    setMsg('')
    setSaving(true)
    try {
      const { rfid_tag, ...patientForm } = form
      const { data: newPatient, error } = await supabase.from('patients').insert(patientForm).select().single()
      if (error) { setMsg(error.message); return }
      if (rfid_tag && rfid_tag.trim()) {
        const { error: tagErr } = await supabase.from('rfid_tags').insert({ tag_token: rfid_tag.trim(), patient_id: newPatient.id, status: 'Active', assigned_at: new Date().toISOString() })
        if (tagErr) { setMsg(tagErr.message); }
      }
      setShow(false)
      setForm({ patient_code: '', name: '', birth_date: '', room: '', bed: '', attending_physician: '', admission_status: 'Admitted', rfid_tag: '' })
      await load()
    } finally {
      setSaving(false)
    }
  }

  const statuses = ['All', 'Admitted', 'Outpatient', 'Discharged']
  const filtered = patients.filter(p => {
    const matchSearch = (p.name + ' ' + p.patient_code).toLowerCase().includes(search.toLowerCase())
    const matchStatus = filter === 'All' || p.admission_status === filter
    return matchSearch && matchStatus
  })

  const counts = {
    All: patients.length,
    Admitted: patients.filter(p => p.admission_status === 'Admitted').length,
    Outpatient: patients.filter(p => p.admission_status === 'Outpatient').length,
    Discharged: patients.filter(p => p.admission_status === 'Discharged').length,
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="eyebrow">Records</div>
          <h1 className="page-title">Patients</h1>
          <p className="page-subtitle">{patients.length} registered patient{patients.length === 1 ? '' : 's'} in the system.</p>
        </div>
        <button className="btn btn-primary" onClick={() => {
          const next = patients.length + 1
          setForm({ patient_code: `PAT-2026-${String(next).padStart(3, '0')}`, name: '', birth_date: '', room: '', bed: '', attending_physician: doctors[0]?.name || '', admission_status: 'Admitted', rfid_tag: '' })
          setShow(true)
        }}>
          <Icon name="plus" size={16} /> Add Patient
        </button>
      </div>

      <div className="stat-grid" style={{ marginBottom: 16 }}>
        <div className="stat-card">
          <div className="stat-icon"><Icon name="users" size={21} /></div>
          <div className="stat-body"><div className="stat-label">Total</div><div className="stat-value">{counts.All}</div><div className="stat-foot">All patient records</div></div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><Icon name="bed" size={21} /></div>
          <div className="stat-body"><div className="stat-label">Admitted</div><div className="stat-value">{counts.Admitted}</div><div className="stat-foot">Currently in the hospital</div></div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><Icon name="clock" size={21} /></div>
          <div className="stat-body"><div className="stat-label">Outpatient</div><div className="stat-value">{counts.Outpatient}</div><div className="stat-foot">Not admitted</div></div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><Icon name="check" size={21} /></div>
          <div className="stat-body"><div className="stat-label">Discharged</div><div className="stat-value">{counts.Discharged}</div><div className="stat-foot">Completed visits</div></div>
        </div>
      </div>

      {show && (
        <div className="modal-backdrop" onClick={() => setShow(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <h3>New Patient</h3>
                <p>Register a patient record.</p>
              </div>
              <button className="modal-close" onClick={() => setShow(false)} aria-label="Close"><Icon name="x" size={16} /></button>
            </div>
            <form onSubmit={add} className="modal-body">
              <div className="form-grid">
                <div className="field"><label>Patient Code</label><input className="input" value={form.patient_code} onChange={e => setForm({ ...form, patient_code: e.target.value })} placeholder="PAT-2026-006" required /></div>
                <div className="field"><label>Full Name</label><input className="input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Juan Dela Cruz" required /></div>
                <div className="field"><label>Birth Date</label><input className="input" type="date" value={form.birth_date} onChange={e => setForm({ ...form, birth_date: e.target.value })} /></div>
                <div className="field"><label>Room</label><input className="input" value={form.room} onChange={e => setForm({ ...form, room: e.target.value })} placeholder="201" /></div>
                <div className="field"><label>Bed</label><input className="input" value={form.bed} onChange={e => setForm({ ...form, bed: e.target.value })} placeholder="A" /></div>
                <div className="field"><label>Attending Physician</label>
                  <select className="select" value={form.attending_physician} onChange={e => setForm({ ...form, attending_physician: e.target.value })}>
                    {doctors.map(d => <option key={d.name} value={d.name}>{d.name}</option>)}
                  </select>
                </div>
                <div className="field"><label>Admission Status</label>
                  <select className="select" value={form.admission_status} onChange={e => setForm({ ...form, admission_status: e.target.value })}>
                    <option>Admitted</option><option>Outpatient</option><option>Discharged</option>
                  </select>
                </div>
                <div className="field"><label>RFID Tag (optional)</label><input className="input" value={form.rfid_tag} onChange={e => setForm({ ...form, rfid_tag: e.target.value })} placeholder="Tag token e.g. 2066071338" /></div>
              </div>
              {msg && <div className="alert alert-error" style={{ marginTop: 14 }}>{msg}</div>}
            </form>
            <div className="modal-foot">
              <button type="button" className="btn btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button type="submit" className="btn btn-success" onClick={add} disabled={saving}>{saving ? 'Saving…' : 'Save Patient'}</button>
            </div>
          </div>
        </div>
      )}

      <div className="toolbar">
        <div className="search">
          <Icon name="search" size={16} />
          <input className="input" placeholder="Search patients by name or code…" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <div className="chips">
          {statuses.map(s => (
            <button key={s} className={'chip' + (filter === s ? ' active' : '')} onClick={() => setFilter(s)}>
              {s} <span style={{ opacity: .7 }}>({counts[s]})</span>
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr><th>Patient</th><th>Code</th><th>Room / Bed</th><th>Physician</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan="6">
                    <div className="empty-state">
                      <span className="ico"><Icon name="users" size={20} /></span>
                      <b>No patients found</b>
                      <span>Try a different search or register a new patient record.</span>
                    </div>
                  </td>
                </tr>
              )}
              {filtered.map(p => (
                <tr key={p.id}>
                  <td>
                    <div className="row" style={{ flexWrap: 'nowrap' }}>
                      <span className="avatar-sm">{initials(p.name)}</span>
                      <span style={{ fontWeight: 600, color: 'var(--ink)' }}>{p.name}</span>
                    </div>
                  </td>
                  <td className="mono">{p.patient_code}</td>
                  <td>{p.room} / {p.bed}</td>
                  <td>{p.attending_physician}</td>
                  <td><span className={'badge ' + (p.admission_status === 'Admitted' ? 'badge-blue' : p.admission_status === 'Outpatient' ? 'badge-amber' : 'badge-gray')}>{p.admission_status}</span></td>
                  <td className="row" style={{ gap: 6 }}>
                    <Link className="btn btn-ghost btn-sm" to={`/patients/${p.id}`}>Open</Link>
                    <button className="btn btn-sm" style={{ background: '#dc2626', color: 'white' }} onClick={() => remove(p.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
