import { useEffect, useState, useCallback, useRef } from 'react'
import Pagination from '../components/Pagination'

function formatDuration(started, ended) {
  if (!started || !ended) return '—'
  const secs = Math.round((new Date(ended) - new Date(started)) / 1000)
  if (secs < 0) return '—'
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function AudioPlayer({ url }) {
  const audioRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)

  const toggle = () => {
    const el = audioRef.current
    if (!el) return
    if (playing) { el.pause() } else { el.play() }
  }

  const onTimeUpdate = () => {
    const el = audioRef.current
    if (!el) return
    setCurrentTime(el.currentTime)
    setProgress(el.duration ? (el.currentTime / el.duration) * 100 : 0)
  }

  const onLoadedMetadata = () => {
    const el = audioRef.current
    if (el) setDuration(el.duration)
  }

  const onEnded = () => setPlaying(false)

  const seek = (e) => {
    const el = audioRef.current
    if (!el || !el.duration) return
    const rect = e.currentTarget.getBoundingClientRect()
    const ratio = (e.clientX - rect.left) / rect.width
    el.currentTime = ratio * el.duration
  }

  const fmt = (s) => {
    if (!s || !isFinite(s)) return '0:00'
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  return (
    <div className="bg-gray-900 rounded-xl px-4 py-3 flex flex-col gap-2">
      <audio
        ref={audioRef}
        src={url}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onTimeUpdate={onTimeUpdate}
        onLoadedMetadata={onLoadedMetadata}
        onEnded={onEnded}
        preload="metadata"
      />
      <div className="flex items-center gap-3">
        {/* Play/Pause */}
        <button
          onClick={toggle}
          className="w-9 h-9 flex items-center justify-center rounded-full bg-indigo-600 hover:bg-indigo-500 flex-shrink-0 transition-colors"
        >
          {playing ? (
            <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
            </svg>
          ) : (
            <svg className="w-4 h-4 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z"/>
            </svg>
          )}
        </button>

        {/* Time */}
        <span className="text-xs text-gray-400 w-10 flex-shrink-0 tabular-nums">{fmt(currentTime)}</span>

        {/* Progress bar */}
        <div
          className="flex-1 h-1.5 bg-gray-700 rounded-full cursor-pointer relative"
          onClick={seek}
        >
          <div
            className="h-full bg-indigo-500 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Duration */}
        <span className="text-xs text-gray-400 w-10 text-right flex-shrink-0 tabular-nums">{fmt(duration)}</span>

        {/* Download */}
        <a
          href={url}
          download
          className="w-8 h-8 flex items-center justify-center rounded-lg bg-gray-700 hover:bg-gray-600 transition-colors"
          title="Download recording"
        >
          <svg className="w-4 h-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
        </a>
      </div>
    </div>
  )
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

  const [selected, setSelected] = useState(null)   // full call detail
  const [transcript, setTranscript] = useState(null)
  const [activeTab, setActiveTab] = useState('transcript')

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

  useEffect(() => { fetchCalls() }, [fetchCalls])

  const openCall = (call) => {
    setSelected(call)
    setTranscript(null)
    setActiveTab(call.recording_url ? 'recording' : 'transcript')
    fetch(`/api/calls/${call.call_sid}`)
      .then(r => r.json())
      .then(data => {
        setSelected(data)
        setTranscript(data?.transcript || [])
      })
      .catch(() => setTranscript([]))
  }

  const closeModal = () => {
    setSelected(null)
    setTranscript(null)
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
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Recording</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Transcript</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {calls.length === 0 && (
                <tr><td colSpan={7} className="px-6 py-10 text-center text-gray-400">No calls found</td></tr>
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
                    {c.recording_url ? (
                      <button
                        onClick={() => openCall(c)}
                        className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 text-xs font-medium"
                        title="Play recording"
                      >
                        <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M8 5v14l11-7z"/>
                        </svg>
                        Play
                      </button>
                    ) : (
                      <span className="text-gray-300 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-6 py-3">
                    <button
                      onClick={() => openCall(c)}
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

      {/* Call Detail Modal */}
      {selected && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={closeModal}>
          <div
            className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div>
                <h3 className="font-semibold text-gray-900">Call Details</h3>
                <p className="text-xs text-gray-500">
                  {selected.phone_number} · {selected.language?.toUpperCase()} · {formatDuration(selected.started_at, selected.ended_at)}
                </p>
              </div>
              <button
                onClick={closeModal}
                className="text-gray-400 hover:text-gray-600 text-xl font-light w-8 h-8 flex items-center justify-center"
              >
                ✕
              </button>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-gray-100 px-6">
              {selected.recording_url && (
                <button
                  onClick={() => setActiveTab('recording')}
                  className={`py-3 px-1 mr-6 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === 'recording'
                      ? 'border-indigo-600 text-indigo-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Recording
                </button>
              )}
              <button
                onClick={() => setActiveTab('transcript')}
                className={`py-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'transcript'
                    ? 'border-indigo-600 text-indigo-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                Transcript
              </button>
            </div>

            {/* Body */}
            <div className="overflow-y-auto flex-1 px-6 py-4">
              {activeTab === 'recording' && selected.recording_url && (
                <div className="py-2">
                  <p className="text-xs text-gray-500 mb-3">Full call audio — guest and Maya mixed</p>
                  <AudioPlayer url={selected.recording_url} />
                </div>
              )}

              {activeTab === 'transcript' && (
                <div className="space-y-3">
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
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
