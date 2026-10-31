import { useEffect, useState } from 'react'
import Pagination from '../components/Pagination'
import { api } from '../lib/api'
import { fmtDateTime, fmtPhone, LeadBadge, INTENT_LABELS } from '../lib/format'

const TABS = [
  ['pending', 'Waiting'],
  ['contacted', 'Contacted'],
  ['not_needed', 'Not needed'],
  ['all', 'All'],
]

function LeadCard({ lead, onStatus, busy }) {
  const details = [
    lead.dates_mentioned && `Dates: ${lead.dates_mentioned}`,
    lead.guests && `${lead.guests} guest${lead.guests > 1 ? 's' : ''}`,
    lead.room_interest,
  ].filter(Boolean)

  return (
    <div className="card-hover bg-white rounded-xl border border-gray-100 p-4 sm:p-5 flex flex-col sm:flex-row sm:items-start justify-between gap-4">
      <div className="flex items-start gap-3 sm:gap-4 min-w-0">
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center font-bold shrink-0 ${
          lead.source === 'whatsapp' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-600'
        }`}>
          {lead.source === 'whatsapp' ? 'W' : '☎'}
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-gray-900 truncate">{lead.guest_name || fmtPhone(lead.phone_number) || 'Unknown caller'}</p>
            {lead.source === 'call' && <LeadBadge lead={lead.lead_temperature} />}
            <span className="text-[10px] font-medium text-gray-400 uppercase tracking-wide">
              {lead.source === 'whatsapp' ? 'WhatsApp' : (INTENT_LABELS[lead.intent] || 'Call')}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            {lead.guest_name && lead.phone_number ? `${fmtPhone(lead.phone_number)} · ` : ''}{fmtDateTime(lead.created_at)}
          </p>
          {(lead.interest_summary || lead.reason) && (
            <p className="text-sm text-gray-700 mt-2">{lead.interest_summary || lead.reason}</p>
          )}
          {details.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {details.map((d, i) => (
                <span key={i} className="text-[11px] font-medium bg-stone-50 text-stone-600 border border-stone-100 rounded-full px-2 py-0.5">{d}</span>
              ))}
            </div>
          )}
          {lead.recording_url && <audio controls preload="none" src={lead.recording_url} className="mt-3 h-8 w-full max-w-xs" />}
          {lead.callback_status === 'contacted' && lead.contacted_at && (
            <p className="text-[11px] text-emerald-600 mt-2">Contacted {fmtDateTime(lead.contacted_at)}</p>
          )}
        </div>
      </div>

      <div className="flex sm:flex-col items-stretch gap-2 shrink-0 sm:w-36">
        {lead.phone_number && (
          <a href={`tel:+${String(lead.phone_number).replace(/\D/g, '')}`}
             className="flex-1 text-center text-xs font-medium bg-brand-dark hover:bg-brand-darker text-white rounded-lg px-3 py-1.5 transition-colors">
            Call guest
          </a>
        )}
        {lead.callback_status === 'pending' ? (
          <>
            <button disabled={busy} onClick={() => onStatus(lead, 'contacted')}
              className="flex-1 text-xs font-medium bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50">
              Mark contacted
            </button>
            <button disabled={busy} onClick={() => onStatus(lead, 'not_needed')}
              className="flex-1 text-xs font-medium border border-gray-200 text-gray-500 hover:bg-gray-50 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50">
              Not needed
            </button>
          </>
        ) : (
          <button disabled={busy} onClick={() => onStatus(lead, 'pending')}
            className="flex-1 text-xs font-medium border border-gray-200 text-gray-500 hover:bg-gray-50 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50">
            Move back to waiting
          </button>
        )}
      </div>
    </div>
  )
}

export default function Callbacks() {
  const [data, setData] = useState({ data: [], page: 1, pages: 1, total: 0 })
  const [page, setPage] = useState(1)
  const [tab, setTab] = useState('pending')
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')

  const load = () => {
    api(`/callbacks?status=${tab}&page=${page}&limit=20`).then(setData).catch(() => {})
  }
  useEffect(() => { load() }, [page, tab])

  const setStatus = async (lead, status) => {
    setBusy(lead.key); setError('')
    try {
      await api(`/callbacks/${lead.source}/${encodeURIComponent(lead.key)}`, {
        method: 'PATCH', body: JSON.stringify({ status }),
      })
      load()
    } catch (err) {
      setError(err.message || 'Could not update')
    } finally { setBusy(null) }
  }

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Callbacks</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Guests who asked about booking, rates or events — on a call or on WhatsApp. Call them back, then mark them contacted.
        </p>
      </div>

      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-lg w-fit">
        {TABS.map(([key, label]) => (
          <button key={key} onClick={() => { setTab(key); setPage(1) }}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
              tab === key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}>
            {label}
          </button>
        ))}
      </div>

      {error && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2 mb-4">{error}</p>
      )}

      {data.total === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 px-6 py-16 text-center">
          <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto mb-3 text-2xl">✓</div>
          <p className="text-sm font-medium text-gray-800">{tab === 'pending' ? 'All caught up' : 'Nothing here yet'}</p>
          <p className="text-xs text-gray-400 mt-1">
            {tab === 'pending' ? 'No guests are waiting for a callback right now.' : 'No guests in this list.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {data.data.map(lead => (
            <LeadCard key={`${lead.source}-${lead.key}`} lead={lead} onStatus={setStatus} busy={busy === lead.key} />
          ))}
          <Pagination page={data.page} pages={data.pages} onPage={setPage} />
        </div>
      )}
    </div>
  )
}
