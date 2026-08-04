import { useEffect, useState, useMemo } from 'react'
import { api } from '../lib/api'

const PAGE_SIZE = 10

function fmt(sec) {
  if (!sec) return '0m'
  const m = Math.floor(sec / 60), s = sec % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function fmtDate(iso) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) }
  catch { return iso }
}

function isoDate(iso) {
  if (!iso) return ''
  try { return new Date(iso).toISOString().slice(0, 10) } catch { return '' }
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
  const map = { paid: 'bg-emerald-100 text-emerald-700', pending: 'bg-amber-100 text-amber-700', failed: 'bg-red-100 text-red-600' }
  return <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${map[status] || 'bg-gray-100 text-gray-500'}`}>{status}</span>
}

function SeverityDot({ s }) {
  return <span className={`inline-block w-2 h-2 rounded-full shrink-0 mt-1 ${s === 'high' ? 'bg-red-500' : 'bg-amber-400'}`} />
}

function Pager({ page, pages, onChange }) {
  if (pages <= 1) return null
  return (
    <div className="flex items-center justify-between px-4 sm:px-6 py-3 border-t border-gray-100 bg-gray-50/50">
      <span className="text-xs text-gray-400">Page {page} of {pages}</span>
      <div className="flex gap-1">
        <button onClick={() => onChange(page - 1)} disabled={page <= 1}
          className="px-2.5 py-1 rounded-lg text-xs font-medium text-gray-600 border border-gray-200 disabled:opacity-30 hover:bg-gray-100 transition-colors">← Prev</button>
        <button onClick={() => onChange(page + 1)} disabled={page >= pages}
          className="px-2.5 py-1 rounded-lg text-xs font-medium text-gray-600 border border-gray-200 disabled:opacity-30 hover:bg-gray-100 transition-colors">Next →</button>
      </div>
    </div>
  )
}

function DateFilter({ from, to, onFrom, onTo, onClear }) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      <span className="text-xs text-gray-500 font-medium">Filter by date:</span>
      <input type="date" value={from} onChange={e => onFrom(e.target.value)}
        className="border border-gray-200 rounded-lg px-2.5 py-1 text-xs text-gray-700 focus:outline-none focus:ring-1 focus:ring-stone-400" />
      <span className="text-xs text-gray-400">to</span>
      <input type="date" value={to} onChange={e => onTo(e.target.value)}
        className="border border-gray-200 rounded-lg px-2.5 py-1 text-xs text-gray-700 focus:outline-none focus:ring-1 focus:ring-stone-400" />
      {(from || to) && (
        <button onClick={onClear} className="text-xs text-stone-600 hover:text-stone-900 underline">Clear</button>
      )}
    </div>
  )
}

function paginate(arr, page) {
  const start = (page - 1) * PAGE_SIZE
  return arr.slice(start, start + PAGE_SIZE)
}

export default function Revenue() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('revenue')

  // Date filters
  const [revFrom, setRevFrom] = useState('')
  const [revTo, setRevTo]     = useState('')
  const [minFrom, setMinFrom] = useState('')
  const [minTo, setMinTo]     = useState('')

  // Pagination pages
  const [paidPage,    setPaidPage]    = useState(1)
  const [pendPage,    setPendPage]    = useState(1)
  const [callPage,    setCallPage]    = useState(1)
  const [flagPage,    setFlagPage]    = useState(1)

  useEffect(() => {
    api('/revenue').then(d => { setData(d); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  // reset pages when filters change
  useEffect(() => { setPaidPage(1); setPendPage(1) }, [revFrom, revTo])
  useEffect(() => { setCallPage(1) }, [minFrom, minTo])

  const filtered = useMemo(() => {
    if (!data) return { paid: [], pend: [], calls: [], flags: [] }
    const inRange = (iso, from, to) => {
      const d = isoDate(iso)
      if (from && d < from) return false
      if (to && d > to) return false
      return true
    }
    const paid  = data.payment_rows.filter(p => p.status === 'paid' && inRange(p.paid_at || p.created_at, revFrom, revTo))
    const pend  = data.payment_rows.filter(p => p.status !== 'paid' && inRange(p.created_at, revFrom, revTo))
    const calls = data.call_rows.filter(c => inRange(c.date, minFrom, minTo))
    const flags = [
      // Unpaid payments (pending > 30 min)
      ...pend.map(p => {
        const ageMin = (Date.now() - new Date(p.created_at).getTime()) / 60000
        if (ageMin < 30) return null
        return {
          type: 'unpaid_payment',
          severity: ageMin > 120 ? 'high' : 'medium',
          label: 'Payment not received',
          detail: `₹${(p.amount_due || 0).toLocaleString('en-IN')} advance pending for ${p.phone} — link sent ${Math.round(ageMin)} min ago`,
          date: p.created_at,
        }
      }).filter(Boolean),
      // Interested but didn't book (from backend flags of type dropped_interest)
      ...(data.flags || []).filter(f => f.type === 'dropped_interest'),
    ].sort((a, b) => (a.severity === 'high' ? 0 : 1) - (b.severity === 'high' ? 0 : 1))

    return { paid, pend, calls, flags }
  }, [data, revFrom, revTo, minFrom, minTo])

  if (loading) return <div className="p-8 text-center text-gray-400 text-sm">Loading revenue data…</div>
  if (!data)   return <div className="p-8 text-center text-red-400 text-sm">Failed to load data.</div>

  const { total_minutes, total_calls, total_collected, total_pending_amount } = data
  const { paid, pend, calls, flags } = filtered

  const paidCollected  = paid.reduce((s, p) => s + (p.amount_paid || 0), 0)
  const pendDue        = pend.reduce((s, p) => s + (p.amount_due || 0), 0)

  // paginated slices
  const paidRows  = paginate(paid,  paidPage),  paidPages  = Math.max(1, Math.ceil(paid.length  / PAGE_SIZE))
  const pendRows  = paginate(pend,  pendPage),  pendPages  = Math.max(1, Math.ceil(pend.length  / PAGE_SIZE))
  const callRows  = paginate(calls, callPage),  callPages  = Math.max(1, Math.ceil(calls.length / PAGE_SIZE))
  const flagRows  = paginate(flags, flagPage),  flagPages  = Math.max(1, Math.ceil(flags.length / PAGE_SIZE))

  return (
    <div className="p-4 sm:p-8 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Revenue & Usage</h1>
        <p className="text-sm text-gray-400 mt-0.5">Payments collected, AI call time, and items needing attention</p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6">
        <StatBox label="Revenue Collected" value={`₹${(total_collected || 0).toLocaleString('en-IN')}`} sub={`${data.payment_rows.filter(p=>p.status==='paid').length} payments`} green />
        <StatBox label="Pending Advance"   value={`₹${(total_pending_amount || 0).toLocaleString('en-IN')}`} sub={`${data.payment_rows.filter(p=>p.status!=='paid').length} unpaid`} red={pend.length > 0} />
        <StatBox label="Total AI Call Time" value={`${total_minutes}m`} sub={`across ${total_calls} calls`} />
        <StatBox label="Needs Attention"   value={flags.length} sub={`${flags.filter(f=>f.severity==='high').length} high priority`} red={flags.length > 0} />
      </div>

      {/* Tab bar */}
      <div className="flex flex-wrap gap-1 bg-gray-100 p-1 rounded-xl mb-6 w-fit">
        {[['revenue','Revenue'],['minutes','Call Minutes'],['flags',`Needs Attention${flags.length ? ` (${flags.length})` : ''}`]].map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)}
            className={`px-3 sm:px-4 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all whitespace-nowrap ${tab===key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Revenue tab ── */}
      {tab === 'revenue' && (
        <div className="space-y-4">
          <DateFilter from={revFrom} to={revTo} onFrom={setRevFrom} onTo={setRevTo} onClear={() => { setRevFrom(''); setRevTo('') }} />

          {/* Paid */}
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
            <div className="px-4 sm:px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">Payments Received</h2>
                <p className="text-xs text-gray-400 mt-0.5">50% advance collected via PayU</p>
              </div>
              <span className="text-sm font-bold text-emerald-600">₹{paidCollected.toLocaleString('en-IN')}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[540px]">
                <thead><tr className="border-b border-gray-50">
                  {['Phone','Advance Paid','Total Booking','Balance at Hotel','Paid At','Status'].map(h => (
                    <th key={h} className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {paidRows.length === 0 && <tr><td colSpan={6} className="px-6 py-10 text-center text-gray-400 text-sm">No payments in this range</td></tr>}
                  {paidRows.map((p, i) => (
                    <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-emerald-50/30 transition-colors">
                      <td className="px-4 sm:px-6 py-3.5 font-medium text-gray-800">{p.phone}</td>
                      <td className="px-4 sm:px-6 py-3.5 font-semibold text-emerald-700">₹{(p.amount_paid||0).toLocaleString('en-IN')}</td>
                      <td className="px-4 sm:px-6 py-3.5 text-gray-600">₹{(p.amount_total||0).toLocaleString('en-IN')}</td>
                      <td className="px-4 sm:px-6 py-3.5 text-gray-500">₹{(p.balance||0).toLocaleString('en-IN')}</td>
                      <td className="px-4 sm:px-6 py-3.5 text-gray-400 text-xs">{fmtDate(p.paid_at)}</td>
                      <td className="px-4 sm:px-6 py-3.5"><Badge status={p.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={paidPage} pages={paidPages} onChange={setPaidPage} />
          </div>

          {/* Pending */}
          <div className="bg-white rounded-xl border border-amber-200 overflow-hidden">
            <div className="px-4 sm:px-6 py-4 border-b border-amber-100 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">Pending Payments</h2>
                <p className="text-xs text-gray-400 mt-0.5">Payment link sent but not yet paid</p>
              </div>
              <span className="text-sm font-bold text-amber-600">₹{pendDue.toLocaleString('en-IN')} due</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[500px]">
                <thead><tr className="border-b border-amber-50">
                  {['Phone','Advance Due','Link Sent','Status'].map(h => (
                    <th key={h} className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {pendRows.length === 0 && <tr><td colSpan={4} className="px-6 py-10 text-center text-gray-400 text-sm">No pending payments</td></tr>}
                  {pendRows.map((p, i) => (
                    <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-amber-50/30 transition-colors">
                      <td className="px-4 sm:px-6 py-3.5 font-medium text-gray-800">{p.phone}</td>
                      <td className="px-4 sm:px-6 py-3.5 font-semibold text-amber-700">₹{(p.amount_due||0).toLocaleString('en-IN')}</td>
                      <td className="px-4 sm:px-6 py-3.5 text-gray-400 text-xs">{fmtDate(p.created_at)}</td>
                      <td className="px-4 sm:px-6 py-3.5"><Badge status={p.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={pendPage} pages={pendPages} onChange={setPendPage} />
          </div>
        </div>
      )}

      {/* ── Call Minutes tab ── */}
      {tab === 'minutes' && (
        <div>
          <DateFilter from={minFrom} to={minTo} onFrom={setMinFrom} onTo={setMinTo} onClear={() => { setMinFrom(''); setMinTo('') }} />
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
            <div className="px-4 sm:px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">Call Duration Log</h2>
                <p className="text-xs text-gray-400 mt-0.5">AI time used per call</p>
              </div>
              <span className="text-sm font-bold text-gray-700">
                {Math.round(calls.reduce((s,c)=>s+(c.duration_sec||0),0)/60*10)/10} min · {calls.length} calls
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[420px]">
                <thead><tr className="border-b border-gray-50">
                  {['Phone','Duration','Language','Date'].map(h => (
                    <th key={h} className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {callRows.length === 0 && <tr><td colSpan={4} className="px-6 py-10 text-center text-gray-400 text-sm">No calls in this range</td></tr>}
                  {callRows.map((c, i) => (
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
            <Pager page={callPage} pages={callPages} onChange={setCallPage} />
          </div>
        </div>
      )}

      {/* ── Needs Attention tab ── */}
      {tab === 'flags' && (
        <div>
          <div className="space-y-3 mb-4">
            {flagRows.length === 0 && (
              <div className="bg-white rounded-xl border border-gray-100 p-10 text-center text-gray-400 text-sm">
                No items needing attention 🎉
              </div>
            )}
            {flagRows.map((f, i) => (
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
          <Pager page={flagPage} pages={flagPages} onChange={setFlagPage} />
        </div>
      )}
    </div>
  )
}
