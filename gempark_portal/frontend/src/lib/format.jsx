// Shared display helpers — the hotel is in Ooty, so times are always shown in IST.
const IST = { timeZone: 'Asia/Kolkata' }

export const fmtDateTime = (raw) =>
  raw ? new Date(raw).toLocaleString('en-IN', { ...IST, dateStyle: 'medium', timeStyle: 'short' }) : '—'

export const fmtDate = (raw) =>
  raw ? new Date(raw).toLocaleDateString('en-IN', { ...IST, dateStyle: 'medium' }) : '—'

// 917820951897 -> +91 78209 51897; anything else is shown as stored.
export function fmtPhone(raw) {
  const d = String(raw || '').replace(/\D/g, '')
  if (d.length === 12 && d.startsWith('91')) return `+91 ${d.slice(2, 7)} ${d.slice(7)}`
  if (d.length === 10) return `+91 ${d.slice(0, 5)} ${d.slice(5)}`
  return raw || ''
}

export function fmtDur(call) {
  let s = call?.duration_seconds
  if (s == null && call?.started_at && call?.ended_at) {
    s = (new Date(call.ended_at) - new Date(call.started_at)) / 1000
  }
  if (s == null || isNaN(s)) return '—'
  s = Math.max(0, Math.round(s))
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

export const LEAD_STYLES = {
  hot:     'bg-red-50 text-red-600 border-red-100',
  warm:    'bg-amber-50 text-amber-700 border-amber-100',
  cold:    'bg-sky-50 text-sky-700 border-sky-100',
  unknown: 'bg-gray-50 text-gray-400 border-gray-100',
}

export const INTENT_LABELS = {
  room_booking: 'Room booking',
  event:        'Event',
  dining:       'Dining',
  information:  'Information',
  other:        'Other',
  unknown:      'Not reviewed',
}

export function LeadBadge({ lead }) {
  const key = lead || 'unknown'
  return (
    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border capitalize ${LEAD_STYLES[key] || LEAD_STYLES.unknown}`}>
      {key === 'unknown' ? 'Not reviewed' : key}
    </span>
  )
}
