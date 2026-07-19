import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Calls from './pages/Calls'
import Bookings from './pages/Bookings'
import Events from './pages/Events'
import Guests from './pages/Guests'
import Analytics from './pages/Analytics'
import WhatsApp from './pages/WhatsApp'
import Settings from './pages/Settings'
import Usage from './pages/Usage'

function DashboardLayout({ children }) {
  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}

function Protected({ page: Page }) {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <Page />
      </DashboardLayout>
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Navigate to="/overview" replace />} />
      <Route path="/overview"  element={<Protected page={Overview}  />} />
      <Route path="/calls"     element={<Protected page={Calls}     />} />
      <Route path="/bookings"  element={<Protected page={Bookings}  />} />
      <Route path="/events"    element={<Protected page={Events}    />} />
      <Route path="/guests"    element={<Protected page={Guests}    />} />
      <Route path="/analytics" element={<Protected page={Analytics} />} />
      <Route path="/whatsapp"  element={<Protected page={WhatsApp}  />} />
      <Route path="/usage"     element={<Protected page={Usage}     />} />
      <Route path="/settings"  element={<Protected page={Settings}  />} />
    </Routes>
  )
}
