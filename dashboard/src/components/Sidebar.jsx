import { NavLink } from 'react-router-dom'

const links = [
  { to: '/overview', label: 'Overview',  icon: '📊' },
  { to: '/calls',    label: 'Calls',     icon: '📞' },
  { to: '/bookings', label: 'Bookings',  icon: '🛏️' },
  { to: '/events',   label: 'Events',    icon: '🎉' },
  { to: '/guests',   label: 'Guests',    icon: '👤' },
]

export default function Sidebar() {
  return (
    <aside className="w-56 bg-slate-900 flex flex-col h-full shrink-0">
      <div className="px-6 py-5 border-b border-slate-700">
        <p className="text-xs text-slate-400 font-medium uppercase tracking-widest">Hotel</p>
        <h1 className="text-white font-bold text-base leading-tight mt-0.5">Voice Agent</h1>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {links.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ` +
              (isActive
                ? 'bg-indigo-600 text-white'
                : 'text-slate-400 hover:bg-slate-800 hover:text-white')
            }
          >
            <span className="text-base">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-6 py-4 border-t border-slate-700">
        <p className="text-xs text-slate-500">Lotus Sutra Goa</p>
      </div>
    </aside>
  )
}
