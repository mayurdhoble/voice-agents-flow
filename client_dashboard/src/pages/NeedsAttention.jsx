import { useEffect, useState } from 'react'
import Pagination from '../components/Pagination'
import { api } from '../lib/api'

export default function NeedsAttention() {
  const [data, setData] = useState({ data: [], page: 1, pages: 1, total: 0 })
  const [page, setPage] = useState(1)

  useEffect(() => {
    api(`/needs-attention?page=${page}&limit=20`).then(setData).catch(() => {})
  }, [page])

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Needs Attention</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Unconfirmed bookings your team should follow up on — before you lose the guest.
        </p>
      </div>

      {data.total === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 px-6 py-16 text-center">
          <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto mb-3 text-2xl">✓</div>
          <p className="text-sm font-medium text-gray-800">All caught up</p>
          <p className="text-xs text-gray-400 mt-1">No bookings need attention right now.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data.data.map(b => (
            <div key={b.id} className="card-hover bg-white rounded-xl border border-gray-100 p-4 sm:p-5 flex items-start justify-between gap-4">
              <div className="flex items-start gap-3 sm:gap-4 min-w-0">
                <div className="w-9 h-9 rounded-lg bg-amber-100 text-amber-600 flex items-center justify-center font-bold shrink-0">!</div>
                <div className="min-w-0">
                  <p className="font-medium text-gray-900 truncate">{b.guests?.name || 'Guest (name not captured)'}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {b.guests?.phone || 'no phone'} · {b.room_type || 'room TBD'} · {b.checkin_date || '?'} → {b.checkout_date || '?'}
                  </p>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {(b.issues || []).map((iss, i) => (
                      <span key={i} className="text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-100 rounded-full px-2 py-0.5">
                        {iss}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="text-right shrink-0">
                {b.guests?.phone && (
                  <a href={`tel:${b.guests.phone}`}
                     className="inline-block text-xs font-medium bg-brand-dark hover:bg-brand-darker text-white rounded-lg px-3 py-1.5 transition-colors">
                    Call guest
                  </a>
                )}
                <p className="text-[11px] text-gray-400 mt-1.5">{b.created_at ? new Date(b.created_at).toLocaleDateString() : ''}</p>
              </div>
            </div>
          ))}
          <Pagination page={data.page} pages={data.pages} onPage={setPage} />
        </div>
      )}
    </div>
  )
}
