export default function Pagination({ page, pages, onPage }) {
  if (pages <= 1) return null

  const nums = () => {
    const out = []
    const left = Math.max(1, page - 2)
    const right = Math.min(pages, page + 2)
    if (left > 1) { out.push(1); if (left > 2) out.push('...') }
    for (let i = left; i <= right; i++) out.push(i)
    if (right < pages) { if (right < pages - 1) out.push('...'); out.push(pages) }
    return out
  }

  return (
    <div className="flex items-center justify-between px-6 py-3 border-t border-gray-100">
      <p className="text-xs text-gray-500">Page {page} of {pages}</p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPage(page - 1)}
          disabled={page === 1}
          className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >← Prev</button>
        {nums().map((n, i) =>
          n === '...' ? (
            <span key={`e-${i}`} className="px-2 py-1.5 text-xs text-gray-400">…</span>
          ) : (
            <button
              key={n}
              onClick={() => onPage(n)}
              className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                n === page ? 'bg-indigo-600 text-white border-indigo-600'
                           : 'border-gray-200 text-gray-600 hover:bg-gray-50'}`}
            >{n}</button>
          )
        )}
        <button
          onClick={() => onPage(page + 1)}
          disabled={page === pages}
          className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >Next →</button>
      </div>
    </div>
  )
}
