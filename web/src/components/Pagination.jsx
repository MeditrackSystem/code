import Icon from './Icon'

export default function Pagination({ page, pageSize, total, onChange, label = 'records' }) {
  if (total <= pageSize) {
    return (
      <div className="table-foot">
        <span>{total} {label}</span>
      </div>
    )
  }
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const from = (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <div className="table-foot">
      <span className="count">Showing <b>{from}–{to}</b> of {total} {label}</span>
      <div className="pager">
        <button onClick={() => onChange(page - 1)} disabled={page <= 1} aria-label="Previous page">
          <Icon name="arrowLeft" size={14} />
        </button>
        <span className="count">Page {page} of {pages}</span>
        <button onClick={() => onChange(page + 1)} disabled={page >= pages} aria-label="Next page">
          <Icon name="chevronRight" size={14} />
        </button>
      </div>
    </div>
  )
}
