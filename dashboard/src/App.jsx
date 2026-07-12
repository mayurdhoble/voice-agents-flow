import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Overview from './pages/Overview'
import Calls from './pages/Calls'
import Bookings from './pages/Bookings'
import Events from './pages/Events'
import Guests from './pages/Guests'

export default function App() {
  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/calls" element={<Calls />} />
          <Route path="/bookings" element={<Bookings />} />
          <Route path="/events" element={<Events />} />
          <Route path="/guests" element={<Guests />} />
        </Routes>
      </main>
    </div>
  )
}
