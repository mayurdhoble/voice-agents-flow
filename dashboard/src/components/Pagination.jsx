export default function Pagination({ page, pages, onPage }) {
  if (pages <= 1) return null

  const getPageNumbers = () => {
    const nums = []
    const delta = 2
    const left = Math.max(1, page - delta)
    const right = Math.min(pages, page + delta)

    if (left > 1) {
      nums.push(1)
      if (left > 2) nums.push('...')
    }
    for (let i = left; i <= right; i++) nums.push(i)
    if (right < pages) {
      if (right < pages - 1) nums.push('...')
      nums.push(pages)
    }
    return nums
  }

  return (
    <div className="flex items-center justify-between px-6 py-3 border-t border-gray-100">
      <p className="text-xs text-gray-500">
        Page {page} of {pages}
      </p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPage(page - 1)}
          disabled={page === 1}
          className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          ← Prev
        </button>

        {getPageNumbers().map((n, i) =>
          n === '...' ? (
            <span key={`ellipsis-${i}`} className="px-2 py-1.5 text-xs text-gray-400">…</span>
          ) : (
            <button
              key={n}
              onClick={() => onPage(n)}
              className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                n === page
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {n}
            </button>
          )
        )}

        <button
          onClick={() => onPage(page + 1)}
          disabled={page === pages}
          className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Next →
        </button>
      </div>
    </div>
  )
}
