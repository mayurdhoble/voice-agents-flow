import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

function Row({ label, value, mono }) {
  return (
    <div className="flex items-center justify-between py-3.5 border-b border-gray-50 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className={`text-sm font-medium text-gray-800 ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
    </div>
  )
}

export default function Settings() {
  const navigate = useNavigate()
  const [backendOk, setBackendOk] = useState(null)
  const [username, setUsername] = useState('—')

  useEffect(() => {
    const token = localStorage.getItem('dashboard_token')
    fetch('/api/me', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => {
        if (!r.ok) throw new Error()
        return r.json()
      })
      .then(d => {
        setBackendOk(true)
        setUsername(d.username || '—')
      })
      .catch(() => setBackendOk(false))
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('dashboard_token')
    navigate('/login', { replace: true })
  }

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Settings</h1>
        <p className="text-sm text-gray-500 mt-0.5">System configuration and session info</p>
      </div>

      {/* Session */}
      <div className="bg-white rounded-xl border border-gray-100 px-6 mb-5">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest pt-4 pb-2">Session</p>
        <Row label="Logged in as" value={username} />
        <Row label="Token storage" value="localStorage" />
        <Row label="Token expiry" value="24 hours" />
        <div className="py-4">
          <button
            onClick={handleLogout}
            className="text-sm font-medium text-red-600 hover:text-red-700 border border-red-200 hover:border-red-300 rounded-lg px-4 py-2 transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>

      {/* Backend */}
      <div className="bg-white rounded-xl border border-gray-100 px-6 mb-5">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest pt-4 pb-2">Backend</p>
        <Row label="API server" value="http://localhost:8002" mono />
        <Row
          label="Connection"
          value={
            backendOk === null ? 'Checking…' :
            backendOk ? 'Connected' : 'Unreachable'
          }
        />
      </div>

      {/* Credentials info */}
      <div className="bg-white rounded-xl border border-gray-100 px-6">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest pt-4 pb-2">Authentication</p>
        <Row label="Username key" value="DASHBOARD_USERNAME" mono />
        <Row label="Password key" value="DASHBOARD_PASSWORD" mono />
        <Row label="JWT secret key" value="DASHBOARD_JWT_SECRET" mono />
        <div className="py-3">
          <p className="text-xs text-gray-400">
            Set these keys in your <span className="font-mono">.env</span> file to change login credentials.
            Restart the backend server after any changes.
          </p>
        </div>
      </div>
    </div>
  )
}
