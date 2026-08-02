import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import Pagination from '../components/Pagination'

const TEMPLATE_LABELS = {
  booking_confirmation: 'Booking Confirmation',
  event_confirmation:   'Event Confirmation',
}

function SentMessages() {
  const [data, setData] = useState({ data: [], page: 1, pages: 1, total: 0 })
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('all')

  useEffect(() => {
    const p = new URLSearchParams({ page, limit: 20 })
    if (statusFilter !== 'all') p.set('status', statusFilter)
    api(`/whatsapp?${p}`).then(setData).catch(() => {})
  }, [page, statusFilter])

  const guestName  = r => r.bookings?.guests?.name || '—'
  const guestPhone = r => r.phone || r.bookings?.guests?.phone || '—'

  return (
    <div>
      <div className="flex gap-2 mb-4">
        {['all', 'sent', 'failed'].map(s => (
          <button key={s}
            onClick={() => { setStatusFilter(s); setPage(1) }}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
              statusFilter === s
                ? 'bg-brand-dark text-white border-brand-dark'
                : 'bg-white text-gray-500 border-gray-200 hover:border-gray-400'
            }`}>
            {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>
      <div className="bg-white rounded-xl border border-gray-100">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[480px]">
            <thead>
              <tr className="border-b border-gray-100">
                {['Guest', 'Phone', 'Message Type', 'Status', 'Sent At'].map(h => (
                  <th key={h} className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.data.length === 0 && (
                <tr><td colSpan={5} className="px-6 py-10 text-center text-gray-400 text-sm">No messages found</td></tr>
              )}
              {data.data.map(row => (
                <tr key={row.id} className="border-b border-gray-50 last:border-0 hover:bg-stone-50/50 transition-colors">
                  <td className="px-4 sm:px-6 py-3.5 font-medium text-gray-800">{guestName(row)}</td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-500 text-xs font-mono">{guestPhone(row)}</td>
                  <td className="px-4 sm:px-6 py-3.5">
                    <span className="text-xs bg-stone-100 text-stone-700 px-2 py-0.5 rounded-full font-medium">
                      {TEMPLATE_LABELS[row.template_name] || row.template_name || '—'}
                    </span>
                  </td>
                  <td className="px-4 sm:px-6 py-3.5">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                      row.status === 'sent' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'
                    }`}>
                      {row.status === 'sent' ? '✓ Sent' : '✗ Failed'}
                    </span>
                  </td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-400 text-xs">
                    {row.sent_at ? new Date(row.sent_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={data.page} pages={data.pages} onPage={setPage} />
      </div>
    </div>
  )
}

function ConversationThread({ phone, onClose }) {
  const [session, setSession] = useState(null)

  useEffect(() => {
    api(`/whatsapp/conversations/${encodeURIComponent(phone)}`).then(setSession).catch(() => {})
  }, [phone])

  if (!session) return (
    <div className="flex items-center justify-center h-40 text-gray-400 text-sm">Loading…</div>
  )

  const conv = session.conversation || []

  return (
    <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
      <div className="flex items-center justify-between px-4 sm:px-5 py-4 border-b border-gray-100">
        <div>
          <p className="font-semibold text-gray-800 text-sm">{session.guest_name || phone}</p>
          <p className="text-xs text-gray-400 font-mono">{phone}</p>
        </div>
        <div className="flex items-center gap-3">
          {session.booking_done && (
            <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">Booking confirmed</span>
          )}
          <button onClick={onClose} className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors">✕</button>
        </div>
      </div>
      <div className="p-4 space-y-3 max-h-96 overflow-y-auto bg-gray-50">
        {conv.length === 0 && <p className="text-center text-gray-400 text-sm py-8">No messages yet</p>}
        {conv.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-xs px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed ${
              msg.role === 'user'
                ? 'bg-brand-dark text-white rounded-br-sm'
                : 'bg-white text-gray-800 border border-gray-200 rounded-bl-sm shadow-sm'
            }`}>
              <p>{msg.content}</p>
              {msg.ts && (
                <p className={`text-[10px] mt-1 ${msg.role === 'user' ? 'text-white/40' : 'text-gray-400'}`}>
                  {new Date(msg.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function BotConversations() {
  const [data, setData] = useState({ data: [], page: 1, pages: 1, total: 0 })
  const [page, setPage] = useState(1)
  const [activePhone, setActivePhone] = useState(null)

  useEffect(() => {
    api(`/whatsapp/conversations?page=${page}&limit=20`).then(setData).catch(() => {})
  }, [page])

  return (
    <div className="space-y-4">
      {activePhone && (
        <ConversationThread phone={activePhone} onClose={() => setActivePhone(null)} />
      )}
      <div className="bg-white rounded-xl border border-gray-100">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[480px]">
            <thead>
              <tr className="border-b border-gray-100">
                {['Guest', 'Phone', 'Messages', 'Booking', 'Last Active'].map(h => (
                  <th key={h} className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.data.length === 0 && (
                <tr><td colSpan={5} className="px-6 py-10 text-center text-gray-400 text-sm">No conversations yet</td></tr>
              )}
              {data.data.map(row => (
                <tr
                  key={row.id}
                  onClick={() => setActivePhone(row.phone)}
                  className="border-b border-gray-50 last:border-0 hover:bg-stone-50 cursor-pointer transition-colors"
                >
                  <td className="px-4 sm:px-6 py-3.5 font-medium text-gray-800">{row.guest_name || '—'}</td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-500 text-xs font-mono">{row.phone}</td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-500">{row.message_count}</td>
                  <td className="px-4 sm:px-6 py-3.5">
                    {row.booking_done
                      ? <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">Confirmed</span>
                      : <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">In progress</span>
                    }
                  </td>
                  <td className="px-4 sm:px-6 py-3.5 text-gray-400 text-xs">
                    {row.last_message_at ? new Date(row.last_message_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={data.page} pages={data.pages} onPage={setPage} />
      </div>
    </div>
  )
}

export default function WhatsApp() {
  const [tab, setTab] = useState('conversations')

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">WhatsApp</h1>
        <p className="text-sm text-gray-400 mt-0.5">Bot conversations and sent notifications</p>
      </div>

      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-lg w-fit">
        {[['conversations', 'Bot Conversations'], ['sent', 'Sent Messages']].map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
              tab === key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'conversations' ? <BotConversations /> : <SentMessages />}
    </div>
  )
}
