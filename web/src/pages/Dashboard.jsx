import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../supabaseClient'
import { getSession } from '../session'
import { formatDateTime, initials } from '../utils'
import Icon from '../components/Icon'

function buildSeries(rows) {
  const days = []
  const now = new Date()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(now.getDate() - i)
    days.push({
      key: d.toISOString().slice(0, 10),
      label: d.toLocaleDateString(undefined, { weekday: 'short' }),
      count: 0,
    })
  }
  const map = Object.fromEntries(days.map(d => [d.key, d]))
  rows.forEach(r => {
    const key = new Date(r.scanned_at).toISOString().slice(0, 10)
    if (map[key]) map[key].count += 1
  })
  return days
}

function AreaChart({ data }) {
  const W = 680, H = 244, L = 36, R = 14, T = 18, B = 32
  const max = Math.max(1, ...data.map(d => d.count))
  const stepX = (W - L - R) / Math.max(1, data.length - 1)
  const y = v => T + (1 - v / max) * (H - T - B)
  const pts = data.map((d, i) => ({ x: L + i * stepX, y: y(d.count), ...d }))
  const line = pts.reduce((acc, p, i, arr) => {
    if (i === 0) return `M ${p.x.toFixed(1)} ${p.y.toFixed(1)}`
    const prev = arr[i - 1]
    const cx = (prev.x + p.x) / 2
    return `${acc} C ${cx.toFixed(1)} ${prev.y.toFixed(1)}, ${cx.toFixed(1)} ${p.y.toFixed(1)}, ${p.x.toFixed(1)} ${p.y.toFixed(1)}`
  }, '')
  const area = `${line} L ${pts[pts.length - 1].x.toFixed(1)} ${H - B} L ${pts[0].x.toFixed(1)} ${H - B} Z`
  const ticks = [1, 0.66, 0.33, 0].map(t => ({ v: Math.round(max * t), y: y(max * t) }))

  return (
    <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="RFID scans over the last 7 days">
      <defs>
        <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.01" />
        </linearGradient>
      </defs>

      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={L} x2={W - R} y1={t.y} y2={t.y} stroke="#e8edf5" strokeWidth="1" strokeDasharray={i === ticks.length - 1 ? '0' : '4 5'} />
          <text x={L - 10} y={t.y + 4} textAnchor="end" fontSize="11" fill="#5a6c85" fontWeight="600">{t.v}</text>
        </g>
      ))}

      <path d={area} fill="url(#areaFill)" />
      <path d={line} fill="none" stroke="#2563eb" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />

      {pts.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r="4.2" fill="#ffffff" stroke="#2563eb" strokeWidth="2.4" />
          <text x={p.x} y={H - 8} textAnchor="middle" fontSize="11" fill="#5a6c85" fontWeight="600">{p.label}</text>
        </g>
      ))}
    </svg>
  )
}

function Donut({ admitted, outpatient, other }) {
  const total = admitted + outpatient + other || 1
  const r = 52, C = 2 * Math.PI * r
  const a = (admitted / total) * C
  const o = (outpatient / total) * C
  return (
    <div className="donut">
      <svg viewBox="0 0 132 132" width="132" height="132">
        <circle cx="66" cy="66" r={r} fill="none" stroke="#eef2f8" strokeWidth="13" />
        {admitted > 0 && (
          <circle cx="66" cy="66" r={r} fill="none" stroke="#1d4ed8" strokeWidth="13"
            strokeDasharray={`${a} ${C}`} strokeLinecap="round" transform="rotate(-90 66 66)" />
        )}
        {outpatient > 0 && (
          <circle cx="66" cy="66" r={r} fill="none" stroke="#7dabf8" strokeWidth="13"
            strokeDasharray={`${o} ${C}`} strokeDashoffset={-a} strokeLinecap="round" transform="rotate(-90 66 66)" />
        )}
      </svg>
      <div className="donut-center">
        <b>{admitted + outpatient + other}</b>
        <span>Patients</span>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const user = getSession()
  const [counts, setCounts] = useState({ patients: 0, tags: 0, scans: 0, users: 0 })
  const [patients, setPatients] = useState([])
  const [tags, setTags] = useState([])
  const [staff, setStaff] = useState([])
  const [orders, setOrders] = useState([])
  const [admins, setAdmins] = useState([])
  const [recent, setRecent] = useState([])
  const [series, setSeries] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const [p, t, s, u, o, r, a, act] = await Promise.all([
        supabase.from('patients').select('*', { count: 'exact' }),
        supabase.from('rfid_tags').select('*', { count: 'exact' }),
        supabase.from('scan_logs').select('*', { count: 'exact', head: true }),
        supabase.from('users').select('*', { count: 'exact', head: true }),
        supabase.from('medication_orders').select('*', { count: 'exact' }),
        supabase.from('scan_logs').select('*').order('scanned_at', { ascending: false }).limit(7),
        supabase.from('medication_administrations').select('*'),
        supabase.from('scan_logs').select('scanned_at').order('scanned_at', { ascending: false }).limit(300),
      ])
      setCounts({
        patients: p.count || 0,
        tags: t.count || 0,
        scans: s.count || 0,
        users: u.count || 0,
      })
      setPatients(p.data || [])
      setTags(t.data || [])
      setStaff(u.data || [])
      setOrders(o.data || [])
      setAdmins(a.data || [])
      setRecent(r.data || [])
      setSeries(buildSeries(act.data || []))
      setLoading(false)
    }
    load()
  }, [])

  const admitted = patients.filter(p => p.admission_status === 'Admitted').length
  const outpatient = patients.filter(p => p.admission_status === 'Outpatient').length
  const other = Math.max(0, patients.length - admitted - outpatient)
  const activeTags = tags.filter(t => t.status === 'Active').length
  const tagPct = tags.length ? Math.round((activeTags / tags.length) * 100) : 0

  const given = admins.filter(a => a.status === 'Given').length
  const missed = admins.filter(a => a.status === 'Missed').length
  const pending = admins.filter(a => a.status === 'Pending').length ||
    Math.max(0, orders.length - new Set(admins.filter(a => a.status === 'Given').map(a => a.order_id)).size)
  const adherence = given + missed ? Math.round((given / (given + missed)) * 100) : 0
  const medMax = Math.max(1, given, missed, pending)

  const stats = [
    { label: 'Patients', value: counts.patients, icon: 'users', foot: `${admitted} admitted · ${outpatient} outpatient` },
    { label: 'RFID Tags', value: counts.tags, icon: 'rfid', foot: `${activeTags} active wristbands` },
    { label: 'Scan Logs', value: counts.scans, icon: 'clipboard', foot: 'Recorded by the Raspberry Pi' },
    { label: 'Staff Accounts', value: counts.users, icon: 'shield', foot: 'Doctors, nurses & admin' },
  ]

  const tagToken = id => tags.find(t => t.id === id)?.tag_token
  const staffName = id => staff.find(u => u.id === id)?.name

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="eyebrow">Overview</div>
          <h1 className="page-title">Good day, {user?.name?.split(' ')[0] || 'User'}</h1>
          <p className="page-subtitle">Here is what is happening across MediTrack today.</p>
        </div>
        <span className={'badge ' + (user?.role === 'Administrator' ? 'badge-blue' : 'badge-gray')}>{user?.role}</span>
      </div>

      <div className="stat-grid">
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

      <div className="dash-grid">
        <div className="card">
          <div className="card-head">
            <div>
              <h3 className="card-title">Scan Activity</h3>
              <p className="card-sub" style={{ marginBottom: 0 }}>RFID scans recorded over the last 7 days.</p>
            </div>
            <span className="badge badge-blue">Live</span>
          </div>
          <div style={{ marginTop: 20 }}>
            <AreaChart data={series.length ? series : [{ label: '', count: 0 }, { label: '', count: 0 }]} />
          </div>
          <div className="chart-legend">
            <div className="item"><span className="dot" style={{ background: '#2563eb' }} /> Scans per day</div>
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">Patient Overview</h3>
          <p className="card-sub">Admission status distribution.</p>
          <div className="donut-wrap">
            <Donut admitted={admitted} outpatient={outpatient} other={other} />
            <div className="legend">
              <div className="legend-item"><span className="legend-dot" style={{ background: '#1d4ed8' }} /><span className="lbl">Admitted</span><b>{admitted}</b></div>
              <div className="legend-item"><span className="legend-dot" style={{ background: '#7dabf8' }} /><span className="lbl">Outpatient</span><b>{outpatient}</b></div>
              <div className="legend-item"><span className="legend-dot" style={{ background: '#dde5ef' }} /><span className="lbl">Other</span><b>{other}</b></div>
            </div>
          </div>
          <div className="divider" />
          <div className="bar-row">
            <div className="bar-top"><span>Active RFID tags</span><span>{tagPct}%</span></div>
            <div className="bar-track"><div className="bar-fill" style={{ width: tagPct + '%' }} /></div>
          </div>
          <div className="bar-row" style={{ marginTop: 14 }}>
            <div className="bar-top"><span>Medication adherence</span><span>{adherence}%</span></div>
            <div className="bar-track"><div className="bar-fill green" style={{ width: adherence + '%' }} /></div>
          </div>
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h3 className="card-title">Medication Monitoring</h3>
          <p className="card-sub">Administration status across {orders.length} active order{orders.length === 1 ? '' : 's'}.</p>
          <div className="bars">
            <div className="bar-row">
              <div className="bar-top"><span>Given</span><span>{given}</span></div>
              <div className="bar-track"><div className="bar-fill green" style={{ width: Math.round((given / medMax) * 100) + '%' }} /></div>
            </div>
            <div className="bar-row">
              <div className="bar-top"><span>Missed</span><span>{missed}</span></div>
              <div className="bar-track"><div className="bar-fill red" style={{ width: Math.round((missed / medMax) * 100) + '%' }} /></div>
            </div>
            <div className="bar-row">
              <div className="bar-top"><span>Pending</span><span>{pending}</span></div>
              <div className="bar-track"><div className="bar-fill amber" style={{ width: Math.round((pending / medMax) * 100) + '%' }} /></div>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">Quick Actions</h3>
          <p className="card-sub">Common tasks for your shift.</p>
          <div className="quick-actions">
            <Link to="/patients" className="quick-action"><Icon name="users" size={18} /> Patients</Link>
            <Link to="/rfid" className="quick-action"><Icon name="rfid" size={18} /> RFID Tags</Link>
            <Link to="/scans" className="quick-action"><Icon name="clipboard" size={18} /> Scan History</Link>
            <Link to="/audit" className="quick-action"><Icon name="shield" size={18} /> Audit Trail</Link>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <div>
            <h3 className="card-title">Recent Scans</h3>
            <p className="card-sub" style={{ marginBottom: 0 }}>Latest RFID wristband scans from the Raspberry Pi.</p>
          </div>
          <Link to="/scans" className="btn btn-ghost btn-sm">View all <Icon name="chevronRight" size={14} /></Link>
        </div>
        <div className="table-scroll" style={{ marginTop: 14 }}>
          <table className="data">
            <thead>
              <tr><th>Time</th><th>Tag</th><th>Recorded by</th><th>Reader</th><th>Outcome</th></tr>
            </thead>
            <tbody>
              {recent.length === 0 && (
                <tr>
                  <td colSpan="5">
                    <div className="empty-state">
                      <span className="ico"><Icon name="rfid" size={20} /></span>
                      <b>No scans recorded yet</b>
                      <span>Scan an RFID wristband on the Raspberry Pi and it will appear here.</span>
                    </div>
                  </td>
                </tr>
              )}
              {recent.map(r => (
                <tr key={r.id}>
                  <td className="mono">{formatDateTime(r.scanned_at)}</td>
                  <td className="mono">{tagToken(r.tag_id) || (r.tag_id ? `#${r.tag_id}` : '—')}</td>
                  <td>{staffName(r.user_id) || <span className="muted">Kiosk</span>}</td>
                  <td>{r.reader_type || '—'}</td>
                  <td><span className={'badge ' + (r.outcome === 'Success' ? 'badge-green' : 'badge-red')}>{r.outcome === 'Success' ? 'Recognized' : r.outcome}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
