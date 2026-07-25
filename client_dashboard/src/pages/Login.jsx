import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setToken } from '../lib/api'

const EyeIcon = ({ off }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    {off
      ? <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></>
      : <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></>}
  </svg>
)

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      const { token } = await api('/login', { method: 'POST', body: JSON.stringify({ username, password }) })
      setToken(token)
      navigate('/overview', { replace: true })
    } catch (err) {
      setError(err.message || 'Could not connect to server')
    } finally { setLoading(false) }
  }

  return (
    <div className="min-h-screen flex bg-white">
      {/* Left — brand panel */}
      <div className="hidden md:flex md:w-1/2 relative overflow-hidden bg-gray-950 text-white flex-col justify-between p-12">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-900/50 via-gray-950 to-violet-950/40" />
        {/* decorative rings */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none">
          <div className="w-[520px] h-[520px] rounded-full border border-white/5" />
          <div className="absolute inset-0 m-auto w-[360px] h-[360px] rounded-full border border-white/5" />
          <div className="absolute inset-0 m-auto w-[200px] h-[200px] rounded-full border border-white/5" />
        </div>

        <p className="relative text-sm text-gray-300">AI receptionist for hotels — every call answered, day and night.</p>

        <div className="relative">
          <h1 className="text-5xl font-semibold leading-tight tracking-tight">
            Your front desk,<br />never sleeps.
          </h1>

          {/* frosted stat card */}
          <div className="mt-10 w-72 rounded-2xl bg-white/10 backdrop-blur border border-white/10 p-5">
            <p className="text-xs text-gray-300">This week</p>
            <p className="text-3xl font-bold mt-1">42 calls</p>
            <div className="flex items-end gap-1.5 h-16 mt-4">
              {[40, 65, 30, 80, 55, 90, 70].map((h, i) => (
                <div key={i} className="flex-1 rounded-t bg-gradient-to-t from-indigo-500 to-violet-400" style={{ height: `${h}%` }} />
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-3">14 bookings · 0 missed</p>
          </div>
        </div>

        <div className="relative flex items-center gap-2.5">
          <div className="w-7 h-7 bg-indigo-600 rounded-lg flex items-center justify-center">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 21h18" /><path d="M5 21V7l8-4v18" /><path d="M19 21V11l-6-4" />
            </svg>
          </div>
          <span className="text-sm font-medium">Lotus Sutra · Owner Portal</span>
        </div>
      </div>

      {/* Right — form */}
      <div className="w-full md:w-1/2 flex flex-col">
        <div className="flex-1 flex items-center justify-center px-6">
          <div className="w-full max-w-sm">
            <div className="md:hidden flex items-center gap-2.5 mb-8">
              <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 21h18" /><path d="M5 21V7l8-4v18" /><path d="M19 21V11l-6-4" />
                </svg>
              </div>
              <span className="font-semibold text-gray-900">Lotus Sutra</span>
            </div>

            <h2 className="text-4xl font-semibold text-gray-900 tracking-tight">Sign In</h2>
            <p className="text-sm text-gray-500 mt-2 mb-8">Welcome back to your Owner Portal.</p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <input
                type="text" autoFocus autoComplete="username" placeholder="Username"
                value={username} onChange={e => setUsername(e.target.value)}
                className="w-full border border-gray-200 rounded-full px-5 py-3.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                required
              />
              <div className="relative">
                <input
                  type={show ? 'text' : 'password'} autoComplete="current-password" placeholder="Password"
                  value={password} onChange={e => setPassword(e.target.value)}
                  className="w-full border border-gray-200 rounded-full px-5 py-3.5 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  required
                />
                <button type="button" onClick={() => setShow(s => !s)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                  <EyeIcon off={show} />
                </button>
              </div>

              {error && <p className="text-sm text-red-600">{error}</p>}

              <button
                type="submit" disabled={loading}
                className="w-full bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 disabled:opacity-60 text-white text-sm font-semibold py-3.5 rounded-full transition-all shadow-lg shadow-indigo-600/20"
              >
                {loading ? 'Signing in…' : 'Sign In'}
              </button>
            </form>
          </div>
        </div>
        <div className="px-8 py-5 flex items-center justify-between text-xs text-gray-400">
          <span>© 2026 Lotus Sutra Goa</span>
          <span>Owner Portal</span>
        </div>
      </div>
    </div>
  )
}
