import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Calls from './pages/Calls'
import Bookings from './pages/Bookings'
import NeedsAttention from './pages/NeedsAttention'
import Guests from './pages/Guests'
import Events from './pages/Events'
import Requests from './pages/Requests'
import WhatsApp from './pages/WhatsApp'
import Settings from './pages/Settings'

function HamburgerIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  )
}

function Layout({ children }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="flex h-screen bg-brand-cream overflow-hidden">
      {/* Mobile backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Sidebar — fixed on mobile (slide-in), static on desktop */}
      <div
        className={`fixed inset-y-0 left-0 z-40 flex-shrink-0 transition-transform duration-300 ease-in-out lg:static lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <Sidebar onClose={() => setOpen(false)} />
      </div>

      {/* Main content area */}
      <div className="flex flex-col flex-1 overflow-hidden min-w-0">
        {/* Mobile top bar */}
        <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-gray-100 lg:hidden shrink-0">
          <button
            onClick={() => setOpen(true)}
            className="p-1.5 rounded-lg text-gray-600 hover:text-gray-900 hover:bg-gray-100 transition-colors"
            aria-label="Open menu"
          >
            <HamburgerIcon />
          </button>
          <img src="/logo.png" alt="Lotus Sutra" className="h-7 w-auto" />
          <span className="text-sm font-semibold text-gray-900 tracking-wide">Lotus Sutra</span>
        </div>

        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}

function Protected({ page: Page }) {
  return (
    <ProtectedRoute>
      <Layout>
        <Page />
      </Layout>
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login"     element={<Login />} />
      <Route path="/"          element={<Navigate to="/overview" replace />} />
      <Route path="/overview"  element={<Protected page={Overview} />} />
      <Route path="/calls"     element={<Protected page={Calls} />} />
      <Route path="/bookings"  element={<Protected page={Bookings} />} />
      <Route path="/attention" element={<Protected page={NeedsAttention} />} />
      <Route path="/guests"    element={<Protected page={Guests} />} />
      <Route path="/events"    element={<Protected page={Events} />} />
      <Route path="/requests"  element={<Protected page={Requests} />} />
      <Route path="/whatsapp"  element={<Protected page={WhatsApp} />} />
      <Route path="/settings"  element={<Protected page={Settings} />} />
      <Route path="*"          element={<Navigate to="/overview" replace />} />
    </Routes>
  )
}
