import { useEffect, useState } from 'react'
import { supabase } from '../supabaseClient'
import { initials } from '../utils'
import Icon from '../components/Icon'

export default function Users() {
  const [users, setUsers] = useState([])
  const [show, setShow] = useState(false)
  const [form, setForm] = useState({ employee_id: '', name: '', username: '', password: '', role: 'Read-only staff', status: 'Active' })
  const [msg, setMsg] = useState({ type: '', text: '' })

  async function load() {
    const { data } = await supabase.from('users').select('*').order('id')
    setUsers(data || [])
  }
  useEffect(() => { load() }, [])

  async function create(e) {
    if (e && e.preventDefault) e.preventDefault()
    setMsg({ type: '', text: '' })
    const { error } = await supabase.from('users').insert(form)
    if (error) { setMsg({ type: 'error', text: error.message }); return }
    setMsg({ type: 'success', text: 'Account created. Give the user their username and password.' })
    setForm({ employee_id: '', name: '', username: '', password: '', role: 'Read-only staff', status: 'Active' })
    setShow(false)
    load()
  }

  async function toggleStatus(u) {
    const status = u.status === 'Active' ? 'Inactive' : 'Active'
    await supabase.from('users').update({ status }).eq('id', u.id)
    load()
  }

  async function remove(u) {
    if (!confirm(`Delete ${u.username}?`)) return
    await supabase.from('users').delete().eq('id', u.id)
    load()
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="eyebrow">Administration</div>
          <h1 className="page-title">User Management</h1>
          <p className="page-subtitle">Admin-only. Create staff accounts and set their passwords.</p>
        </div>
        <div className="row">
          <span className="badge badge-blue">{users.length} accounts</span>
          <button className="btn btn-primary" onClick={() => {
            const next = users.length + 1
            const eid = `U${String(next + 7).padStart(3, '0')}`
            setForm({ employee_id: eid, name: '', username: '', password: '', role: 'Read-only staff', status: 'Active' })
            setShow(true)
          }}>
            <Icon name="plus" size={16} /> Create Account
          </button>
        </div>
      </div>

      <div className="stat-grid" style={{ marginBottom: 16 }}>
        <div className="stat-card">
          <div className="stat-icon"><Icon name="users" size={21} /></div>
          <div className="stat-body"><div className="stat-label">Total Accounts</div><div className="stat-value">{users.length}</div><div className="stat-foot">All staff roles</div></div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><Icon name="check" size={21} /></div>
          <div className="stat-body"><div className="stat-label">Active</div><div className="stat-value">{users.filter(u => u.status === 'Active').length}</div><div className="stat-foot">Can sign in</div></div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><Icon name="shield" size={21} /></div>
          <div className="stat-body"><div className="stat-label">Administrators</div><div className="stat-value">{users.filter(u => u.role === 'Administrator').length}</div><div className="stat-foot">Full access</div></div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><Icon name="stethoscope" size={21} /></div>
          <div className="stat-body"><div className="stat-label">Clinical Staff</div><div className="stat-value">{users.filter(u => ['Doctor', 'Nurse', 'Pharmacist'].includes(u.role)).length}</div><div className="stat-foot">Doctors, nurses, pharmacists</div></div>
        </div>
      </div>

      {msg.text && !show && <div className={'alert ' + (msg.type === 'error' ? 'alert-error' : 'alert-success')}>{msg.text}</div>}

      {show && (
        <div className="modal-backdrop" onClick={() => setShow(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <h3>Create Account</h3>
                <p>The user will log in with this username and password.</p>
              </div>
              <button className="modal-close" onClick={() => setShow(false)} aria-label="Close"><Icon name="x" size={16} /></button>
            </div>
            <form onSubmit={create} className="modal-body">
              <div className="form-grid">
                <div className="field"><label>Employee ID</label><input className="input" value={form.employee_id} onChange={e => setForm({ ...form, employee_id: e.target.value })} placeholder="U008" /></div>
                <div className="field"><label>Full Name</label><input className="input" value={form.name} onChange={e => {
                  const name = e.target.value
                  const slug = name.toLowerCase().replace(/[^a-z]/g, '')
                  const suffix = users.length + 1
                  setForm({ ...form, name, username: slug ? `${slug}${suffix}` : form.username })
                }} placeholder="Nurse Jane Doe" required /></div>
                <div className="field"><label>Username</label><input className="input" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} placeholder="jane.doe" required /></div>
                <div className="field"><label>Password</label><input className="input" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} placeholder="Set a password" required /></div>
                <div className="field"><label>Role</label>
                  <select className="select" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>
                    <option>Administrator</option><option>Doctor</option><option>Nurse</option><option>Pharmacist</option><option>Read-only staff</option>
                  </select>
                </div>
              </div>
              {msg.text && <div className={'alert ' + (msg.type === 'error' ? 'alert-error' : 'alert-success')} style={{ marginTop: 14 }}>{msg.text}</div>}
            </form>
            <div className="modal-foot">
              <button type="button" className="btn btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button type="button" className="btn btn-success" onClick={create}>Create Account</button>
            </div>
          </div>
        </div>
      )}

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr><th>Employee ID</th><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td className="mono">{u.employee_id || '—'}</td>
                  <td>
                    <div className="row" style={{ flexWrap: 'nowrap' }}>
                      <span className="avatar-sm">{initials(u.name)}</span>
                      <span style={{ fontWeight: 600, color: 'var(--ink)' }}>{u.name}</span>
                    </div>
                  </td>
                  <td className="mono">{u.username}</td>
                  <td><span className={'badge ' + (u.role === 'Administrator' ? 'badge-blue' : u.role === 'Read-only staff' ? 'badge-gray' : 'badge-blue')}>{u.role}</span></td>
                  <td><span className={'badge ' + (u.status === 'Active' ? 'badge-green' : 'badge-gray')}>{u.status}</span></td>
                  <td>
                    <div className="row">
                      <button className="btn btn-ghost btn-sm" onClick={() => toggleStatus(u)}>{u.status === 'Active' ? 'Deactivate' : 'Activate'}</button>
                      <button className="btn btn-danger btn-sm" onClick={() => remove(u)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
