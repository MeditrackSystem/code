import { useEffect, useState } from 'react'
import { supabase } from '../supabaseClient'
import Icon from '../components/Icon'

export default function RFIDTags() {
  const [tags, setTags] = useState([])
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('All')

  async function load() {
    const { data } = await supabase.from('rfid_tags').select('*, patients(name,patient_code)').order('id')
    setTags(data || [])
  }
  useEffect(() => { load() }, [])

  async function toggle(t) {
    const status = t.status === 'Active' ? 'Inactive' : 'Active'
    await supabase.from('rfid_tags').update({ status, deactivated_at: status === 'Inactive' ? new Date().toISOString() : null }).eq('id', t.id)
    load()
  }

  const counts = {
    All: tags.length,
    Active: tags.filter(t => t.status === 'Active').length,
    Inactive: tags.filter(t => t.status !== 'Active').length,
  }
  const filtered = tags.filter(t => {
    const match = (t.tag_token + ' ' + (t.patients?.name || '') + ' ' + (t.patients?.patient_code || '')).toLowerCase().includes(search.toLowerCase())
    const matchStatus = filter === 'All' || (filter === 'Active' ? t.status === 'Active' : t.status !== 'Active')
    return match && matchStatus
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="eyebrow">Devices</div>
          <h1 className="page-title">RFID Tags</h1>
          <p className="page-subtitle">Wristbands linked to patient records.</p>
        </div>
      </div>

      <div className="stat-grid" style={{ marginBottom: 16 }}>
        <div className="stat-card">
          <div className="stat-icon"><Icon name="rfid" size={21} /></div>
          <div className="stat-body"><div className="stat-label">Total Tags</div><div className="stat-value">{counts.All}</div><div className="stat-foot">Registered wristbands</div></div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><Icon name="check" size={21} /></div>
          <div className="stat-body"><div className="stat-label">Active</div><div className="stat-value">{counts.Active}</div><div className="stat-foot">Ready to scan</div></div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><Icon name="alert" size={21} /></div>
          <div className="stat-body"><div className="stat-label">Inactive</div><div className="stat-value">{counts.Inactive}</div><div className="stat-foot">Disabled or replaced</div></div>
        </div>
      </div>

      <div className="toolbar">
        <div className="search">
          <Icon name="search" size={16} />
          <input className="input" placeholder="Search tag token or patient…" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <div className="chips">
          {['All', 'Active', 'Inactive'].map(s => (
            <button key={s} className={'chip' + (filter === s ? ' active' : '')} onClick={() => setFilter(s)}>{s} <span style={{ opacity: .7 }}>({counts[s]})</span></button>
          ))}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr><th>Tag Token</th><th>Patient</th><th>Status</th><th>Assigned</th><th></th></tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan="5">
                    <div className="empty-state">
                      <span className="ico"><Icon name="rfid" size={20} /></span>
                      <b>No RFID tags found</b>
                      <span>Assign a wristband from a patient record to see it here.</span>
                    </div>
                  </td>
                </tr>
              )}
              {filtered.map(t => (
                <tr key={t.id}>
                  <td className="mono">{t.tag_token}</td>
                  <td>{t.patients ? <><b>{t.patients.name}</b> <span className="muted">({t.patients.patient_code})</span></> : <span className="muted">Unassigned</span>}</td>
                  <td><span className={'badge ' + (t.status === 'Active' ? 'badge-green' : 'badge-gray')}>{t.status}</span></td>
                  <td className="mono">{t.assigned_at ? new Date(t.assigned_at).toLocaleDateString() : '—'}</td>
                  <td><button className="btn btn-ghost btn-sm" onClick={() => toggle(t)}>{t.status === 'Active' ? 'Deactivate' : 'Activate'}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
