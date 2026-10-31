import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { api, clearToken } from '../lib/api'

const Icon = ({ d, children }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    {children || <path d={d} />}
  </svg>
)

const GridIcon = () => (
  <Icon><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
    <rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /></Icon>
)
const PhoneIcon = () => <Icon d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.6 3.45 2 2 0 0 1 3.54 1h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 8.5a16 16 0 0 0 5.55 5.55l.86-.86a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 21 16.92z" />
const LogoutIcon = () => (
  <Icon><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" /></Icon>
)
const CallbackIcon = () => (
  <Icon><polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" /></Icon>
)
const MessageIcon = () => (
  <Icon><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></Icon>
)
const SettingsIcon = () => (
  <Icon><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></Icon>
)
const CloseIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
)

const links = [
  { to: '/overview',  label: 'Overview',  Icon: GridIcon },
  { to: '/calls',     label: 'Calls',     Icon: PhoneIcon },
  { to: '/callbacks', label: 'Callbacks', Icon: CallbackIcon, badge: true },
  { to: '/whatsapp',  label: 'WhatsApp',  Icon: MessageIcon },
  { to: '/settings',  label: 'Settings',  Icon: SettingsIcon },
]

export default function Sidebar({ onClose }) {
  const navigate = useNavigate()
  const [hotel, setHotel] = useState('Hotel Gem Park, Ooty')
  const [attention, setAttention] = useState(0)

  useEffect(() => {
    api('/overview')
      .then(d => { setAttention(d.callbacks_pending || 0); if (d.hotel) setHotel(d.hotel) })
      .catch(() => {})
  }, [])

  const logout = () => { clearToken(); navigate('/login', { replace: true }) }

  return (
    <aside className="w-64 bg-brand-dark flex flex-col h-full shrink-0">
      {/* Header with logo */}
      <div className="px-5 py-5 border-b border-white/10 relative">
        <div className="flex items-center gap-3">
          <img src="/logo-bg.jpeg" alt="AutomatedGuest AI" className="h-10 w-auto shrink-0 rounded-md" />
          <div className="min-w-0">
            <p className="text-white font-semibold text-sm leading-tight truncate">{hotel}</p>
            <p className="text-brand-blue/70 text-xs mt-0.5">Owner Portal</p>
          </div>
        </div>
        {/* Mobile close button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-4 text-white/50 hover:text-white transition-colors lg:hidden"
          aria-label="Close menu"
        >
          <CloseIcon />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        <p className="px-3 pb-2 text-[10px] font-semibold text-white/30 uppercase tracking-widest">Menu</p>
        {links.map(({ to, label, Icon, badge }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onClose}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ` +
              (isActive
                ? 'bg-brand-blue text-white shadow-sm'
                : 'text-white/60 hover:bg-white/8 hover:text-white')
            }
          >
            <Icon />
            <span className="flex-1">{label}</span>
            {badge && attention > 0 && (
              <span className="text-[10px] font-bold bg-white text-brand-blue rounded-full px-1.5 py-0.5 min-w-[18px] text-center">
                {attention}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-3 py-4 border-t border-white/10 space-y-0.5">
        <p className="px-3 pb-1.5 text-[10px] font-semibold text-white/30 uppercase tracking-widest">Ooty, Tamil Nadu</p>
        <button
          onClick={logout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-white/50 hover:bg-white/8 hover:text-white/80 transition-all"
        >
          <LogoutIcon />
          Sign out
        </button>
      </div>
    </aside>
  )
}
