import { useEffect, useState } from 'react'
import { api } from '../lib/api'

function fmt(sec) {
  if (!sec) return '0m'
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function fmtDate(iso) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) }
  catch { return iso }
}

function StatBox({ label, value, sub, green, red }) {
  return (
    <div className={`rounded-xl border p-4 sm:p-5 ${green ? 'bg-emerald-50 border-emerald-200' : red ? 'bg-red-50 border-red-200' : 'bg-white border-gray-100'}`}>
      <p className={`text-xs font-medium uppercase tracking-wide mb-1 ${green ? 'text-emerald-600' : red ? 'text-red-500' : 'text-gray-400'}`}>{label}</p>
      <p className={`text-2xl font-bold ${green ? 'text-emerald-700' : red ? 'text-red-600' : 'text-gray-900'}`}>{value ?? '—'}</p>
      {sub && <p className={`text-xs mt-0.5 ${green ? 'text-emerald-600' : red ? 'text-red-400' : 'text-gray-400'}`}>{sub}</p>}
    </div>
  )
}

function Badge({ status }) {
  const map = {
    paid:    'bg-emerald-100 text-emerald-700',
    pending: 'bg-amber-100 text-amber-700',
    failed:  'bg-red-100 text-red-600',
  }
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${map[status] || 'bg-gray-100 text-gray-500'}`}>
      {status}
    </span>
  )
}

function SeverityDot({ s }) {
  return <span className={`inline-block w-2 h-2 rounded-full shrink-0 mt-1 ${s === 'high' ? 'bg-red-500' : 'bg-amber-400'}`} />
}

export default function Revenue() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('revenue') // revenue | minutes | flags

  useEffect(() => {
    api('/revenue').then(d => { setData(d); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="p-8 text-center text-gray-400 text-sm">Loading revenue data…</div>
  )
  if (!data) return (
    <div className="p-8 text-center text-red-400 text-sm">Failed to load data. Check backend.</div>
  )

  const { total_minutes, total_calls, total_collected, total_pending_amount, call_rows, payment_rows, flags } = data
  const paid_payments = payment_rows.filter(p => p.status === 'paid')
  const pending_payments = payment_rows.filter(p => p.status === 'pending')

  return (
    <div className="p-4 sm:p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Revenue & Usage</h1>
        <p className="text-sm text-gray-400 mt-0.5">Payments collected, AI call time, and items needing attention</p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6">
        <StatBox label="Revenue Collected" value={`₹${(total_collected || 0).toLocaleString('en-IN')}`} sub={`${paid_payments.length} payment${paid_payments.length !== 1 ? 's' : ''}`} green />
        <StatBox label="Pending Advance" value={`₹${(total_pending_amount || 0).toLocaleString('en-IN')}`} sub={`${pending_payments.length} unpaid link${pending_payments.length !== 1 ? 's' : ''}`} red={pending_payments.length > 0} />
        <StatBox label="Total AI Call Time" value={`${total_minutes}m`} sub={`across ${total_calls} calls`} />
        <StatBox label="Needs Attention" value={flags.length} sub={flags.filter(f => f.severity === 'high').length + ' high priority'} red={flags.length > 0} />
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl mb-6 w-fit">
        {[['revenue', 'Revenue'], ['minutes', 'Call Minutes'], ['flags', `Needs Attention${flags.length ? ` (${flags.length})` : ''}`]].map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)}
            className={`px-3 sm:px-4 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all ${tab === key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Revenue tab ── */}
      {tab === 'revenue' && (
        <div className="space-y-4">
          {/* Paid payments */}
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
            <div className="px-4 sm:px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">Payments Received</h2>
                <p className="text-xs text-gray-400 mt-0.5">50% advance collected via PayU</p>
              </div>
              <span className="text-sm font-bold text-emerald-600">₹{(total_collected || 0).toLocaleString('en-IN')}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[540px]">
                <thead>
                  <tr className="border-b border-gray-50">
                    <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Phone</th>
                    <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Advance Paid</th>
                    <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Total Booking</th>
                    <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Balance at Hotel</th>
                    <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Paid At</th>
                    <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {paid_payments.length === 0 && (
                    <tr><td colSpan={6} className="px-6 py-10 text-center text-gray-400 text-sm">No payments received yet</td></tr>
                  )}
                  {paid_payments.map((p, i) => (
                    <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-emerald-50/30 transition-colors">
                      <td className="px-4 sm:px-6 py-3.5 font-medium text-gray-800">{p.phone}</td>
                      <td className="px-4 sm:px-6 py-3.5 font-semibold text-emerald-700">₹{(p.amount_paid || 0).toLocaleString('en-IN')}</td>
                      <td className="px-4 sm:px-6 py-3.5 text-gray-600">₹{(p.amount_total || 0).toLocaleString('en-IN')}</td>
                      <td className="px-4 sm:px-6 py-3.5 text-gray-500">₹{(p.balance || 0).toLocaleString('en-IN')}</td>
                      <td className="px-4 sm:px-6 py-3.5 text-gray-400 text-xs">{fmtDate(p.paid_at)}</td>
                      <td className="px-4 sm:px-6 py-3.5"><Badge status={p.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pending payments */}
          {pending_payments.length > 0 && (
            <div className="bg-white rounded-xl border border-amber-200 overflow-hidden">
              <div className="px-4 sm:px-6 py-4 border-b border-amber-100 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-gray-900">Pending Payments</h2>
                  <p className="text-xs text-gray-400 mt-0.5">Payment link sent but not yet paid</p>
                </div>
                <span className="text-sm font-bold text-amber-600">₹{(total_pending_amount || 0).toLocaleString('en-IN')} due</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[500px]">
                  <thead>
                    <tr className="border-b border-amber-50">
                      <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Phone</th>
                      <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Advance Due</th>
                      <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Link Sent</th>
                      <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pending_payments.map((p, i) => (
                      <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-amber-50/30 transition-colors">
                        <td className="px-4 sm:px-6 py-3.5 font-medium text-gray-800">{p.phone}</td>
                        <td className="px-4 sm:px-6 py-3.5 font-semibold text-amber-700">₹{(p.amount_due || 0).toLocaleString('en-IN')}</td>
                        <td className="px-4 sm:px-6 py-3.5 text-gray-400 text-xs">{fmtDate(p.created_at)}</td>
                        <td className="px-4 sm:px-6 py-3.5"><Badge status={p.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Call Minutes tab ── */}
      {tab === 'minutes' && (
        <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
          <div className="px-4 sm:px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Call Duration Log</h2>
              <p className="text-xs text-gray-400 mt-0.5">AI time used per call</p>
            </div>
            <span className="text-sm font-bold text-gray-700">{total_minutes} min total</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[420px]">
              <thead>
                <tr className="border-b border-gray-50">
                  <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Phone</th>
                  <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Duration</th>
                  <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Language</th>
                  <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Date</th>
                </tr>
              </thead>
              <tbody>
                {call_rows.length === 0 && (
                  <tr><td colSpan={4} className="px-6 py-10 text-center text-gray-400 text-sm">No calls yet</td></tr>
                )}
                {call_rows.map((c, i) => (
                  <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-stone-50/50 transition-colors">
                    <td className="px-4 sm:px-6 py-3.5 font-medium text-gray-800">{c.phone}</td>
                    <td className="px-4 sm:px-6 py-3.5 font-semibold text-gray-700">{fmt(c.duration_sec)}</td>
                    <td className="px-4 sm:px-6 py-3.5 text-xs font-medium text-gray-500 uppercase tracking-wide">{c.language}</td>
                    <td className="px-4 sm:px-6 py-3.5 text-gray-400 text-xs">{fmtDate(c.date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Needs Attention tab ── */}
      {tab === 'flags' && (
        <div className="space-y-3">
          {flags.length === 0 && (
            <div className="bg-white rounded-xl border border-gray-100 p-10 text-center text-gray-400 text-sm">
              No items needing attention 🎉
            </div>
          )}
          {flags.map((f, i) => (
            <div key={i} className={`bg-white rounded-xl border p-4 sm:p-5 flex gap-3 items-start ${f.severity === 'high' ? 'border-red-200' : 'border-amber-200'}`}>
              <SeverityDot s={f.severity} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className={`text-sm font-semibold ${f.severity === 'high' ? 'text-red-700' : 'text-amber-700'}`}>{f.label}</span>
                  <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-full ${f.severity === 'high' ? 'bg-red-100 text-red-600' : 'bg-amber-100 text-amber-600'}`}>{f.severity}</span>
                </div>
                <p className="text-xs text-gray-500 leading-relaxed">{f.detail}</p>
                {f.date && <p className="text-[10px] text-gray-400 mt-1">{fmtDate(f.date)}</p>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
