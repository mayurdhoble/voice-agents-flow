import { useEffect, useState } from 'react'
import Pagination from '../components/Pagination'
import { api } from '../lib/api'

function fmtDur(a, b) {
  if (!a || !b) return '—'
  try {
    const s = Math.max(0, (new Date(b) - new Date(a)) / 1000)
    const m = Math.floor(s / 60)
    return `${m}m ${Math.round(s % 60)}s`
  } catch { return '—' }
}

function CallDrawer({ call, onClose }) {
  const [detail, setDetail] = useState(null)
  useEffect(() => {
    setDetail(null)
    if (call) api(`/calls/${call.call_sid}`).then(setDetail).catch(() => setDetail({}))
  }, [call])
  if (!call) return null

  const transcript = Array.isArray(detail?.transcript) ? detail.transcript : []

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-white h-full shadow-2xl flex flex-col">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">{call.phone_number || 'Unknown caller'}</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              {call.created_at ? new Date(call.created_at).toLocaleString() : '—'} · {fmtDur(call.started_at, call.ended_at)} · {(call.language || '—').toUpperCase()}
            </p>
          </div>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors text-xl leading-none">×</button>
        </div>

        {call.recording_url && (
          <div className="px-6 py-4 border-b border-gray-100">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Recording</p>
            <audio controls src={call.recording_url} className="w-full" />
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-4">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">Conversation</p>
          {!detail && <p className="text-sm text-gray-400">Loading…</p>}
          {detail && transcript.length === 0 && <p className="text-sm text-gray-400">No transcript available.</p>}
          <div className="space-y-3">
            {transcript.map((m, i) => {
              const isGuest = m.role === 'user'
              return (
                <div key={i} className={`flex ${isGuest ? 'justify-start' : 'justify-end'}`}>
                  <div className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-sm ${
                    isGuest
                      ? 'bg-gray-100 text-gray-800 rounded-tl-sm'
                      : 'bg-brand-dark text-white rounded-tr-sm'
                  }`}>
                    <p className={`text-[10px] font-semibold uppercase tracking-wide mb-0.5 ${isGuest ? 'text-gray-400' : 'text-white/50'}`}>
                      {isGuest ? 'Guest' : 'Maya'}
                    </p>
                    {m.content}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Calls() {
  const [data, setData] = useState({ data: [], page: 1, pages: 1, total: 0 })
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)

  const load = () => {
    const p = new URLSearchParams({ page, limit: 20 })
    if (search) p.set('search', search)
    api(`/calls?${p}`).then(setData).catch(() => {})
  }
  useEffect(() => { load() }, [page])
  useEffect(() => { const t = setTimeout(() => { setPage(1); load() }, 400); return () => clearTimeout(t) }, [search])

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto">
      <div className="mb-6 flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Calls</h1>
          <p className="text-sm text-gray-400 mt-0.5">{data.total} calls · click a row to hear the recording &amp; read the transcript</p>
        </div>
        <input
          value={search} onChange={e => setSearch(e.target.value)} placeholder="Search phone…"
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-full sm:w-56 focus:outline-none focus:ring-2 focus:ring-stone-800 focus:border-transparent hover:border-gray-300 transition-colors"
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-100">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[520px]">
            <thead>
              <tr className="border-b border-gray-100">
                {['Phone', 'Language', 'Duration', 'Recording', 'Time'].map(h => (
                  <th key={h} className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.data.length === 0 && (
                <tr><td colSpan={5} className="px-6 py-10 text-center text-gray-400 text-sm">No calls found</td></tr>
              )}
              {data.data.map(c => (
                <tr key={c.id} onClick={() => setSelected(c)}
                    className="border-b border-gray-50 last:border-0 hover:bg-stone-50 cursor-pointer transition-colors">
                  <td className="px-4 sm:px-6 py-3.5 font-medium text-gray-800">{c.phone_number || '—'}</td>
                  <td className="px-4 sm:px-6 py-3.5 text-xs font-medium text-gray-500 uppercase tracking-wide">{c.language || '—'}</td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-500 text-xs">{fmtDur(c.started_at, c.ended_at)}</td>
                  <td className="px-4 sm:px-6 py-3.5">
                    {c.recording_url ? (
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-700">
                        <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-brand-dark shadow-sm hover:bg-brand-burgundy transition-colors">
                          <svg className="w-3 h-3 fill-white ml-0.5" viewBox="0 0 16 16">
                            <path d="M3 2.5l10 5.5-10 5.5V2.5z"/>
                          </svg>
                        </span>
                        Play
                      </span>
                    ) : <span className="text-gray-300 text-xs">—</span>}
                  </td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-400 text-xs">{c.created_at ? new Date(c.created_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={data.page} pages={data.pages} onPage={setPage} />
      </div>

      <CallDrawer call={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
