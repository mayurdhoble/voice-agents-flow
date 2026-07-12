import { useEffect, useState } from 'react'

export default function Calls() {
  const [calls, setCalls] = useState([])
  const [selected, setSelected] = useState(null)
  const [transcript, setTranscript] = useState(null)

  useEffect(() => {
    fetch('/api/calls?limit=100').then(r => r.json()).then(setCalls).catch(console.error)
  }, [])

  const openTranscript = (call) => {
    setSelected(call)
    fetch(`/api/calls/${call.call_sid}`)
      .then(r => r.json())
      .then(data => setTranscript(data?.transcript || []))
      .catch(() => setTranscript([]))
  }

  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Calls</h2>
      <p className="text-sm text-gray-500 mb-6">{calls.length} calls recorded</p>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left">
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Phone</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Direction</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Language</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Started</th>
              <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Transcript</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {calls.length === 0 && (
              <tr><td colSpan={5} className="px-6 py-10 text-center text-gray-400">No calls yet</td></tr>
            )}
            {calls.map(c => (
              <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-3 font-medium text-gray-800">{c.phone_number || '—'}</td>
                <td className="px-6 py-3">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                    c.direction === 'outbound' ? 'bg-blue-50 text-blue-700' : 'bg-green-50 text-green-700'
                  }`}>{c.direction}</span>
                </td>
                <td className="px-6 py-3 uppercase text-gray-600">{c.language}</td>
                <td className="px-6 py-3 text-gray-500 whitespace-nowrap">
                  {c.started_at ? new Date(c.started_at).toLocaleString() : '—'}
                </td>
                <td className="px-6 py-3">
                  <button
                    onClick={() => openTranscript(c)}
                    className="text-indigo-600 hover:text-indigo-800 text-xs font-medium"
                  >View →</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
              <button onClick={() => { setSelected(null); setTranscript(null) }}
                className="text-gray-400 hover:text-gray-600 text-xl font-light">✕</button>
            </div>
            <div className="overflow-y-auto flex-1 px-6 py-4 space-y-3">
              {!transcript && <p className="text-center text-gray-400 py-8">Loading…</p>}
              {transcript?.length === 0 && <p className="text-center text-gray-400 py-8">No transcript</p>}
              {transcript?.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-start' : 'justify-end'}`}>
                  <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm ${
                    msg.role === 'user'
                      ? 'bg-gray-100 text-gray-800 rounded-tl-sm'
                      : 'bg-indigo-600 text-white rounded-tr-sm'
                  }`}>
                    <p className="text-[10px] font-semibold mb-1 opacity-60">
                      {msg.role === 'user' ? 'Guest' : 'Aria'}
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
