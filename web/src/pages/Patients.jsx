import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../supabaseClient'
import { initials } from '../utils'
import Icon from '../components/Icon'

export default function Patients() {
  const [patients, setPatients] = useState([])
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('All')
  const [form, setForm] = useState({ patient_code: '', name: '', birth_date: '', room: '', bed: '', attending_physician: '', admission_status: 'Admitted' })
  const [show, setShow] = useState(false)
  const [msg, setMsg] = useState('')

  async function load() {
    const { data } = await supabase.from('patients').select('*').order('id')
    setPatients(data || [])
  }
  useEffect(() => { load() }, [])

  async function add(e) {
    if (e && e.preventDefault) e.preventDefault()
    setMsg('')
    const { error } = await supabase.from('patients').insert(form)
    if (error) { setMsg(error.message); return }
    setShow(false)
    setForm({ patient_code: '', name: '', birth_date: '', room: '', bed: '', attending_physician: '', admission_status: 'Admitted' })
    load()
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
        <button className="btn btn-primary" onClick={() => setShow(true)}>
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
                <div className="field"><label>Attending Physician</label><input className="input" value={form.attending_physician} onChange={e => setForm({ ...form, attending_physician: e.target.value })} placeholder="Dr. Maria Santos" /></div>
                <div className="field"><label>Admission Status</label>
                  <select className="select" value={form.admission_status} onChange={e => setForm({ ...form, admission_status: e.target.value })}>
                    <option>Admitted</option><option>Outpatient</option><option>Discharged</option>
                  </select>
                </div>
              </div>
              {msg && <div className="alert alert-error" style={{ marginTop: 14 }}>{msg}</div>}
            </form>
            <div className="modal-foot">
              <button type="button" className="btn btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button type="submit" className="btn btn-success" onClick={add}>Save Patient</button>
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
                  <td><Link className="btn btn-ghost btn-sm" to={`/patients/${p.id}`}>Open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
