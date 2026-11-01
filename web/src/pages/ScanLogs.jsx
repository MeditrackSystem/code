import { useEffect, useMemo, useState } from 'react'
import { supabase } from '../supabaseClient'
import { formatDateTime } from '../utils'
import Icon from '../components/Icon'
import Pagination from '../components/Pagination'

const PAGE_SIZE = 20

export default function ScanLogs() {
  const [rows, setRows] = useState([])
  const [tags, setTags] = useState([])
  const [staff, setStaff] = useState([])
  const [filter, setFilter] = useState('All')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  async function load() {
    const [logs, tagRows, userRows] = await Promise.all([
      supabase.from('scan_logs').select('*').order('scanned_at', { ascending: false }).limit(300),
      supabase.from('rfid_tags').select('id, tag_token'),
      supabase.from('users').select('id, name'),
    ])
    setRows(logs.data || [])
    setTags(tagRows.data || [])
    setStaff(userRows.data || [])
    setLoading(false)
    setRefreshing(false)
  }

  useEffect(() => { load() }, [])

  function refresh() { setRefreshing(true); load() }

  const tagToken = id => tags.find(t => t.id === id)?.tag_token
  const staffName = id => staff.find(u => u.id === id)?.name

  const success = rows.filter(r => r.outcome === 'Success').length
  const failed = rows.length - success

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter(r => {
      const match = !q || (tagToken(r.tag_id) || '').toLowerCase().includes(q) ||
        (staffName(r.user_id) || '').toLowerCase().includes(q)
      const matchOutcome = filter === 'All' ||
        (filter === 'Recognized' && r.outcome === 'Success') ||
        (filter === 'Unknown Tag' && r.outcome !== 'Success')
      return match && matchOutcome
    })
  }, [rows, search, filter, tags, staff])

  useEffect(() => { setPage(1) }, [search, filter])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  const stats = [
    { label: 'Total Scans', value: rows.length, icon: 'clipboard', color: 'blue', foot: 'All recorded scans' },
    { label: 'Recognized', value: success, icon: 'check', color: 'green', foot: 'Patient record opened' },
    { label: 'Unrecognized', value: failed, icon: 'alert', color: 'red', foot: 'Unknown or inactive tag' },
  ]

  const colorMap = {
    blue: { bg: 'var(--brand-50)', fg: 'var(--brand-700)' },
    green: { bg: 'var(--green-bg)', fg: 'var(--green-700)' },
    red: { bg: 'var(--red-bg)', fg: 'var(--red-700)' },
  }

  const filters = [
    ['All', rows.length],
    ['Recognized', success],
    ['Unknown Tag', failed],
  ]

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="eyebrow">Activity / History</div>
          <h1 className="page-title">Scan Logs</h1>
          <p className="page-subtitle">Monitor and review RFID scanning activity recorded by the MediTrack kiosk.</p>
        </div>
        <button className="btn btn-ghost" onClick={refresh} disabled={refreshing}>
          <Icon name="refresh" size={16} /> {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div className="stat-grid" style={{ marginBottom: 16 }}>
        {stats.map(s => {
          const c = colorMap[s.color]
          return (
            <div className="stat-card" key={s.label}>
              <div className="stat-icon" style={{ background: c.bg, color: c.fg }}>
                <Icon name={s.icon} size={21} />
              </div>
              <div className="stat-body">
                <div className="stat-label">{s.label}</div>
                <div className="stat-value">{s.value}</div>
                <div className="stat-foot">{s.foot}</div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="toolbar">
        <div className="search">
          <Icon name="search" size={16} />
          <input
            className="input"
            placeholder="Search by RFID tag token or staff / kiosk name…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch('')}
              aria-label="Clear search"
              style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)', width: 26, height: 26, border: 'none', background: 'transparent', color: 'var(--muted)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6 }}
            >
              <Icon name="x" size={14} />
            </button>
          )}
        </div>
        <div className="chips">
          {filters.map(([label, count]) => (
            <button key={label} className={'chip' + (filter === label ? ' active' : '')} onClick={() => setFilter(label)}>
              {label} <span>({count})</span>
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>Time</th>
                <th>Tag Token</th>
                <th>Recorded By</th>
                <th>Reader</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {visible.length === 0 && (
                <tr>
                  <td colSpan="5">
                    <div className="empty-state">
                      <span className="ico"><Icon name={loading ? 'refresh' : 'clipboard'} size={20} /></span>
                      <b>{loading ? 'Loading scan history…' : 'No scan logs found'}</b>
                      {!loading && <span>Scans appear here as soon as the Raspberry Pi syncs a wristband read.</span>}
                    </div>
                  </td>
                </tr>
              )}
              {visible.map(r => {
                const recognized = r.outcome === 'Success'
                return (
                  <tr key={r.id}>
                    <td className="mono">{formatDateTime(r.scanned_at)}</td>
                    <td className="mono">{tagToken(r.tag_id) || (r.tag_id ? `#${r.tag_id}` : '—')}</td>
                    <td>{staffName(r.user_id) || <span className="muted">Kiosk</span>}</td>
                    <td>{r.reader_type || '—'}</td>
                    <td>
                      <span className={'badge ' + (recognized ? 'badge-green' : 'badge-red')} style={{ gap: 5 }}>
                        <Icon name={recognized ? 'check' : 'alert'} size={12} />
                        {recognized ? 'Recognized' : 'Unknown Tag'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <Pagination page={safePage} pageSize={PAGE_SIZE} total={filtered.length} onChange={setPage} label="scans" />
      </div>
    </div>
  )
}
