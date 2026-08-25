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

const SparkBar = ({ h, delay }) => (
  <div
    className="flex-1 rounded-t bg-brand-blue/30"
    style={{ height: `${h}%`, animationDelay: delay }}
  />
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
      {/* Left — brand panel (desktop only) — WHITE */}
      <div className="hidden lg:flex lg:w-5/12 xl:w-1/2 relative overflow-hidden bg-white text-brand-dark flex-col justify-between p-12 border-r border-brand-border">
        {/* Subtle blue tint overlay */}
        <div className="absolute inset-0 opacity-10"
          style={{ backgroundImage: 'radial-gradient(circle at 25% 75%, #2B7FFF 0%, transparent 55%), radial-gradient(circle at 80% 15%, #0A1628 0%, transparent 50%)' }} />

        {/* Top tagline */}
        <p className="relative text-sm text-brand-dark/50 tracking-wide">
          AI receptionist for hotels — every call answered, day and night.
        </p>

        {/* Center content */}
        <div className="relative">
          {/* Logo large */}
          <div className="mb-8 flex justify-start">
            <img src="/logo.png" alt="AutomatedGuest AI" className="h-24 w-auto" />
          </div>

          <h1 className="text-4xl xl:text-5xl font-light leading-tight tracking-tight text-brand-dark/80">
            Your front desk,<br />
            <span className="font-semibold text-brand-dark">never sleeps.</span>
          </h1>

          {/* Stat card */}
          <div className="mt-10 w-72 rounded-2xl bg-brand-soft backdrop-blur border border-brand-border p-5">
            <p className="text-xs text-brand-dark/40 uppercase tracking-widest">This week</p>
            <p className="text-3xl font-bold mt-1 text-brand-dark">42 calls</p>
            <div className="flex items-end gap-1.5 h-14 mt-4">
              {[40, 65, 30, 80, 55, 90, 70].map((h, i) => (
                <SparkBar key={i} h={h} delay={`${i * 80}ms`} />
              ))}
            </div>
            <p className="text-xs text-brand-dark/30 mt-3">14 bookings · 0 missed</p>
          </div>
        </div>

        {/* Bottom branding */}
        <div className="relative flex items-center gap-2.5">
          <img src="/logo.png" alt="" className="h-7 w-auto opacity-70" />
          <span className="text-sm text-brand-dark/50 tracking-wide">AutomatedGuest AI Clients Portal</span>
        </div>
      </div>

      {/* Right — form — DARK */}
      <div className="w-full lg:w-7/12 xl:w-1/2 flex flex-col bg-brand-dark">
        <div className="flex-1 flex items-center justify-center px-6 py-12">
          <div className="w-full max-w-sm">
            {/* Mobile logo */}
            <div className="lg:hidden flex flex-col items-center gap-3 mb-10">
              <img src="/logo.png" alt="AutomatedGuest AI" className="h-16 w-auto" />
              <p className="text-xs text-white/40 tracking-widest uppercase">Clients Portal</p>
            </div>

            <h2 className="text-3xl font-semibold text-white tracking-tight">Sign In</h2>
            <p className="text-sm text-white/40 mt-2 mb-8">Welcome back to your Clients Portal.</p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <input
                  type="text" autoFocus autoComplete="username" placeholder="Username"
                  value={username} onChange={e => setUsername(e.target.value)}
                  className="w-full bg-white/8 border border-white/15 rounded-xl px-4 py-3.5 text-sm text-white placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-brand-blue focus:border-transparent transition-shadow hover:border-white/25"
                  required
                />
              </div>
              <div className="relative">
                <input
                  type={show ? 'text' : 'password'} autoComplete="current-password" placeholder="Password"
                  value={password} onChange={e => setPassword(e.target.value)}
                  className="w-full bg-white/8 border border-white/15 rounded-xl px-4 py-3.5 pr-12 text-sm text-white placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-brand-blue focus:border-transparent transition-shadow hover:border-white/25"
                  required
                />
                <button type="button" onClick={() => setShow(s => !s)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/80 transition-colors">
                  <EyeIcon off={show} />
                </button>
              </div>

              {error && (
                <p className="text-sm text-red-400 bg-red-900/30 border border-red-500/30 rounded-lg px-3 py-2">{error}</p>
              )}

              <button
                type="submit" disabled={loading}
                className="w-full bg-brand-blue hover:bg-blue-500 disabled:opacity-60 text-white text-sm font-semibold py-3.5 rounded-xl transition-all shadow-sm hover:shadow-md active:scale-[0.99]"
              >
                {loading ? 'Signing in…' : 'Sign In'}
              </button>
            </form>

            <div className="mt-8 pt-6 border-t border-white/10 flex items-center gap-3">
              <img src="/logo.png" alt="" className="h-6 w-auto opacity-50" />
              <p className="text-xs text-white/30">Powered by AutomatedGuest AI</p>
            </div>
          </div>
        </div>

        <div className="px-8 py-5 flex items-center justify-between text-xs text-white/20">
          <span>© 2026 AutomatedGuest AI</span>
          <span>Clients Portal</span>
        </div>
      </div>
    </div>
  )
}
