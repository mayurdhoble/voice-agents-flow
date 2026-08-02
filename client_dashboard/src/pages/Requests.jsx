import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import Pagination from '../components/Pagination'

const TYPE_LABELS = {
  airport_pickup: { label: 'Airport Pickup',  color: 'bg-blue-100 text-blue-700' },
  cab:            { label: 'Cab / Taxi',       color: 'bg-purple-100 text-purple-700' },
  extra_bed:      { label: 'Extra Bed',        color: 'bg-yellow-100 text-yellow-700' },
  early_checkin:  { label: 'Early Check-in',   color: 'bg-orange-100 text-orange-700' },
  late_checkout:  { label: 'Late Check-out',   color: 'bg-pink-100 text-pink-700' },
  restaurant:     { label: 'Restaurant',       color: 'bg-green-100 text-green-700' },
  laundry:        { label: 'Laundry',          color: 'bg-teal-100 text-teal-700' },
  room_service:   { label: 'Room Service',     color: 'bg-stone-100 text-stone-700' },
  event:          { label: 'Event',            color: 'bg-rose-100 text-rose-700' },
  other:          { label: 'Other',            color: 'bg-gray-100 text-gray-600' },
}

const STATUS_STYLES = {
  new:          'bg-amber-100 text-amber-700',
  acknowledged: 'bg-blue-100 text-blue-700',
  handled:      'bg-emerald-100 text-emerald-700',
}

const FILTERS = ['all', 'airport_pickup', 'cab', 'extra_bed', 'early_checkin', 'late_checkout', 'restaurant', 'laundry', 'room_service', 'event', 'other']

export default function Requests() {
  const [data, setData] = useState({ data: [], page: 1, pages: 1, total: 0 })
  const [page, setPage] = useState(1)
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [updating, setUpdating] = useState(null)

  const load = () => {
    const p = new URLSearchParams({ page, limit: 20 })
    if (typeFilter !== 'all') p.set('request_type', typeFilter)
    if (statusFilter !== 'all') p.set('status', statusFilter)
    api(`/requests?${p}`).then(setData).catch(() => {})
  }

  useEffect(() => { load() }, [page, typeFilter, statusFilter])

  const updateStatus = async (id, status) => {
    setUpdating(id)
    try {
      await api(`/requests/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) })
      load()
    } catch {}
    setUpdating(null)
  }

  const typeInfo = (t) => TYPE_LABELS[t] || TYPE_LABELS.other

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Requests</h1>
        <p className="text-sm text-gray-400 mt-0.5">{data.total} service requests captured from calls</p>
      </div>

      {/* Type filter chips */}
      <div className="flex flex-wrap gap-2 mb-4">
        {FILTERS.map(f => (
          <button key={f}
            onClick={() => { setTypeFilter(f); setPage(1) }}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
              typeFilter === f
                ? 'bg-brand-dark text-white border-brand-dark'
                : 'bg-white text-gray-500 border-gray-200 hover:border-gray-400 hover:text-gray-700'
            }`}>
            {f === 'all' ? 'All Types' : (TYPE_LABELS[f]?.label || f)}
          </button>
        ))}
      </div>

      {/* Status filter */}
      <div className="flex flex-wrap gap-2 mb-6">
        {['all', 'new', 'acknowledged', 'handled'].map(s => (
          <button key={s}
            onClick={() => { setStatusFilter(s); setPage(1) }}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
              statusFilter === s
                ? 'bg-brand-dark text-white border-brand-dark'
                : 'bg-white text-gray-500 border-gray-200 hover:border-gray-400 hover:text-gray-700'
            }`}>
            {s === 'all' ? 'All Statuses' : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      {/* Cards */}
      <div className="space-y-3">
        {data.data.length === 0 && (
          <div className="bg-white rounded-xl border border-gray-100 px-6 py-10 text-center text-gray-400 text-sm">
            No requests found
          </div>
        )}
        {data.data.map(r => (
          <div key={r.id} className="card-hover bg-white rounded-xl border border-gray-100 px-4 sm:px-5 py-4 flex items-start gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${typeInfo(r.request_type).color}`}>
                  {typeInfo(r.request_type).label}
                </span>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_STYLES[r.status] || STATUS_STYLES.new}`}>
                  {r.status || 'new'}
                </span>
              </div>
              <p className="text-sm text-gray-800 mt-1">{r.details || '—'}</p>
              <p className="text-xs text-gray-400 mt-1.5">
                {r.guest_name || 'Unknown guest'}
                {r.date_needed ? ` · Needed: ${r.date_needed}` : ''}
                {r.created_at ? ` · ${new Date(r.created_at).toLocaleString()}` : ''}
              </p>
            </div>
            <div className="flex flex-col gap-1.5 shrink-0">
              {r.status !== 'handled' && (
                <>
                  {r.status === 'new' && (
                    <button
                      disabled={updating === r.id}
                      onClick={() => updateStatus(r.id, 'acknowledged')}
                      className="text-xs px-3 py-1.5 rounded-lg border border-blue-200 text-blue-600 hover:bg-blue-50 transition-colors disabled:opacity-50">
                      Acknowledge
                    </button>
                  )}
                  <button
                    disabled={updating === r.id}
                    onClick={() => updateStatus(r.id, 'handled')}
                    className="text-xs px-3 py-1.5 rounded-lg border border-emerald-200 text-emerald-600 hover:bg-emerald-50 transition-colors disabled:opacity-50">
                    Mark Handled
                  </button>
                </>
              )}
              {r.status === 'handled' && (
                <button
                  disabled={updating === r.id}
                  onClick={() => updateStatus(r.id, 'new')}
                  className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-400 hover:bg-gray-50 transition-colors disabled:opacity-50">
                  Reopen
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4">
        <Pagination page={data.page} pages={data.pages} onPage={setPage} />
      </div>
    </div>
  )
}
