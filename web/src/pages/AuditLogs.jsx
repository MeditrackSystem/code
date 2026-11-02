import { useEffect, useMemo, useState } from 'react'
import { supabase } from '../supabaseClient'
import { formatDateTime } from '../utils'
import Icon from '../components/Icon'
import Pagination from '../components/Pagination'

const PAGE_SIZE = 20

const ACTION_LABEL = {
  LOGIN: 'Signed in',
  VIEW_PATIENT: 'Viewed patient',
  SCAN_RFID: 'Scanned RFID',
  ADD_MEDICATION: 'Added medication',
  UPDATE_PATIENT: 'Updated patient',
  ADMINISTER_MEDICATION: 'Administered dose',
  CREATE_USER: 'Created account',
}

export default function AuditLogs() {
  const [rows, setRows] = useState([])
  const [staff, setStaff] = useState([])
  const [filter, setFilter] = useState('All')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const [logs, userRows] = await Promise.all([
        supabase.from('audit_logs').select('*').order('occurred_at', { ascending: false }).limit(100),
        supabase.from('users').select('id, name, role'),
      ])
      setRows(logs.data || [])
      setStaff(userRows.data || [])
      setLoading(false)
    }
    load()
  }, [])

  const staffName = id => staff.find(u => u.id === id)?.name
  const label = action => ACTION_LABEL[action] || action?.replaceAll('_', ' ').toLowerCase() || '—'

  const actions = ['All', ...Array.from(new Set(rows.map(r => r.action).filter(Boolean)))]
  const uniqueUsers = new Set(rows.map(r => r.user_id).filter(Boolean)).size

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return rows.filter(r => {
      const matchQuery = !q || (staffName(r.user_id) || '').toLowerCase().includes(q) ||
        (r.action || '').toLowerCase().includes(q) ||
        (r.record_type || '').toLowerCase().includes(q)
      const matchAction = filter === 'All' || r.action === filter
      return matchQuery && matchAction
    })
  }, [rows, search, filter, staff])

  const stats = [
    { label: 'Events', value: rows.length, icon: 'file', foot: 'Latest 300 records' },
    { label: 'Staff Involved', value: uniqueUsers, icon: 'users', foot: 'Accounts with recorded actions' },
    { label: 'Action Types', value: Math.max(0, actions.length - 1), icon: 'activity', foot: 'Distinct operations' },
  ]

  useEffect(() => { setPage(1) }, [search, filter])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="eyebrow">Security</div>
          <h1 className="page-title">Audit Logs</h1>
          <p className="page-subtitle">A tamper-evident trail of who did what, and when.</p>
        </div>
      </div>

      <div className="stat-grid" style={{ marginBottom: 16 }}>
        {stats.map(s => (
          <div className="stat-card" key={s.label}>
            <div className="stat-icon"><Icon name={s.icon} size={21} /></div>
            <div className="stat-body">
              <div className="stat-label">{s.label}</div>
              <div className="stat-value">{s.value}</div>
              <div className="stat-foot">{s.foot}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="toolbar">
        <div className="search">
          <Icon name="search" size={16} />
          <input className="input" placeholder="Search staff, action or record type…" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
      </div>

      <div className="chips" style={{ marginBottom: 16 }}>
        {actions.map(a => (
          <button key={a} className={'chip' + (filter === a ? ' active' : '')} onClick={() => setFilter(a)}>
            {a === 'All' ? 'All events' : label(a)}
          </button>
        ))}
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr><th>Time</th><th>Staff</th><th>Action</th><th>Record</th><th>Record ID</th></tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan="5">
                    <div className="empty-state">
                      <span className="ico"><Icon name={loading ? 'refresh' : 'shield'} size={20} /></span>
                      <b>{loading ? 'Loading audit trail…' : 'No audit events found'}</b>
                      {!loading && <span>Sign-ins, record edits and scans are logged here automatically.</span>}
                    </div>
                  </td>
                </tr>
              )}
              {visible.map(r => (
                <tr key={r.id}>
                  <td className="mono">{formatDateTime(r.occurred_at)}</td>
                  <td>{staffName(r.user_id) || <span className="muted">System</span>}</td>
                  <td><span className="badge badge-blue">{label(r.action)}</span></td>
                  <td style={{ textTransform: 'capitalize' }}>{r.record_type?.replaceAll('_', ' ') || '—'}</td>
                  <td className="mono">{r.record_id || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={safePage} pageSize={PAGE_SIZE} total={filtered.length} onChange={setPage} label="events" />
      </div>
    </div>
  )
}
