import { useEffect, useState, useCallback } from 'react'
import Pagination from '../components/Pagination'

function formatDuration(started, ended) {
  if (!started || !ended) return '—'
  const secs = Math.round((new Date(ended) - new Date(started)) / 1000)
  if (secs < 0) return '—'
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

export default function Calls() {
  const [calls, setCalls] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)

  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [direction, setDirection] = useState('')
  const [language, setLanguage] = useState('')

  const [selected, setSelected] = useState(null)
  const [transcript, setTranscript] = useState(null)

  // Debounce search input 400ms
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput)
      setPage(1)
    }, 400)
    return () => clearTimeout(t)
  }, [searchInput])

  const fetchCalls = useCallback(() => {
    const params = new URLSearchParams({ page, limit: 20 })
    if (search) params.set('search', search)
    if (direction) params.set('direction', direction)
    if (language) params.set('language', language)

    fetch(`/api/calls?${params}`)
      .then(r => r.json())
      .then(d => {
        setCalls(d.data || [])
        setTotal(d.total || 0)
        setPages(d.pages || 1)
      })
      .catch(console.error)
  }, [page, search, direction, language])

  useEffect(() => {
    fetchCalls()
  }, [fetchCalls])

  const openTranscript = (call) => {
    setSelected(call)
    setTranscript(null)
    fetch(`/api/calls/${call.call_sid}`)
      .then(r => r.json())
      .then(data => setTranscript(data?.transcript || []))
      .catch(() => setTranscript([]))
  }

  const handleFilterChange = (setter) => (e) => {
    setter(e.target.value)
    setPage(1)
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Calls</h1>
        <p className="text-sm text-gray-500 mt-0.5">{total} calls recorded</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <input
          type="text"
          placeholder="Search phone number…"
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          className="border border-gray-200 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 w-56"
        />
        <select
          value={direction}
          onChange={handleFilterChange(setDirection)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        >
          <option value="">All directions</option>
          <option value="inbound">Inbound</option>
          <option value="outbound">Outbound</option>
        </select>
        <select
          value={language}
          onChange={handleFilterChange(setLanguage)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        >
          <option value="">All languages</option>
          <option value="en">English</option>
          <option value="hi">Hindi</option>
          <option value="mr">Marathi</option>
        </select>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left">
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Phone</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Direction</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Language</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Started</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Duration</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Transcript</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {calls.length === 0 && (
                <tr><td colSpan={6} className="px-6 py-10 text-center text-gray-400">No calls found</td></tr>
              )}
              {calls.map(c => (
                <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-3 font-medium text-gray-800">{c.phone_number || '—'}</td>
                  <td className="px-6 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                      c.direction === 'outbound' ? 'bg-blue-50 text-blue-700' : 'bg-green-50 text-green-700'
                    }`}>{c.direction}</span>
                  </td>
                  <td className="px-6 py-3 uppercase text-gray-600">{c.language || '—'}</td>
                  <td className="px-6 py-3 text-gray-500 whitespace-nowrap">
                    {c.started_at ? new Date(c.started_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-6 py-3 text-gray-500 whitespace-nowrap">
                    {formatDuration(c.started_at, c.ended_at)}
                  </td>
                  <td className="px-6 py-3">
                    <button
                      onClick={() => openTranscript(c)}
                      className="text-indigo-600 hover:text-indigo-800 text-xs font-medium"
                    >
                      View →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={page} pages={pages} onPage={setPage} />
      </div>

      {/* Transcript Modal */}
      {selected && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div>
                <h3 className="font-semibold text-gray-900">Transcript</h3>
                <p className="text-xs text-gray-500">{selected.phone_number} · {selected.language?.toUpperCase()}</p>
              </div>
              <button
                onClick={() => { setSelected(null); setTranscript(null) }}
                className="text-gray-400 hover:text-gray-600 text-xl font-light"
              >
                ✕
              </button>
            </div>
            <div className="overflow-y-auto flex-1 px-6 py-4 space-y-3">
              {!transcript && <p className="text-center text-gray-400 py-8">Loading…</p>}
              {transcript?.length === 0 && <p className="text-center text-gray-400 py-8">No transcript available</p>}
              {transcript?.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-start' : 'justify-end'}`}>
                  <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm ${
                    msg.role === 'user'
                      ? 'bg-gray-100 text-gray-800 rounded-tl-sm'
                      : 'bg-indigo-600 text-white rounded-tr-sm'
                  }`}>
                    <p className="text-[10px] font-semibold mb-1 opacity-60">
                      {msg.role === 'user' ? 'Guest' : 'Maya'}
                    </p>
                    {msg.content}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
