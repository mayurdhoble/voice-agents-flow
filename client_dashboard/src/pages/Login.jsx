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

const SparkBar = ({ h }) => (
  <div className="flex-1 rounded-t" style={{ height: `${h}%`, background: 'linear-gradient(to top, #2B7FFF, #60A5FA)' }} />
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

  /* ── Shared form markup ── */
  const FormContent = ({ dark }) => (
    <>
      <div className="mb-6">
        <h2 className={`text-2xl font-bold tracking-tight ${dark ? 'text-white' : 'text-brand-dark'}`}>Welcome back</h2>
        <p className={`text-sm mt-1 ${dark ? 'text-white/40' : 'text-slate-400'}`}>Sign in to your Clients Portal</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className={`block text-[10px] font-semibold mb-1.5 uppercase tracking-widest ${dark ? 'text-white/40' : 'text-slate-400'}`}>Username</label>
          <input
            type="text" autoFocus autoComplete="username" placeholder="Enter your username"
            value={username} onChange={e => setUsername(e.target.value)}
            className={`w-full rounded-xl px-4 py-3.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue transition-all ${dark ? 'text-white placeholder-white/25' : 'text-brand-dark placeholder-slate-300 border border-brand-border'}`}
            style={dark ? { background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.12)' } : { background: '#F5F8FF' }}
            required
          />
        </div>
        <div>
          <label className={`block text-[10px] font-semibold mb-1.5 uppercase tracking-widest ${dark ? 'text-white/40' : 'text-slate-400'}`}>Password</label>
          <div className="relative">
            <input
              type={show ? 'text' : 'password'} autoComplete="current-password" placeholder="Enter your password"
              value={password} onChange={e => setPassword(e.target.value)}
              className={`w-full rounded-xl px-4 py-3.5 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue transition-all ${dark ? 'text-white placeholder-white/25' : 'text-brand-dark placeholder-slate-300 border border-brand-border'}`}
              style={dark ? { background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.12)' } : { background: '#F5F8FF' }}
              required
            />
            <button type="button" onClick={() => setShow(s => !s)}
              className={`absolute right-4 top-1/2 -translate-y-1/2 transition-colors ${dark ? 'text-white/30 hover:text-white/70' : 'text-slate-400 hover:text-slate-600'}`}>
              <EyeIcon off={show} />
            </button>
          </div>
        </div>
        {error && (
          <p className="text-sm text-red-500 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</p>
        )}
        <button
          type="submit" disabled={loading}
          className="w-full text-white text-sm font-semibold py-3.5 rounded-xl transition-all active:scale-[0.99] mt-1"
          style={{ background: 'linear-gradient(135deg, #2B7FFF, #1a6be0)', boxShadow: '0 4px 20px rgba(43,127,255,0.35)' }}
        >
          {loading ? 'Signing in…' : 'Sign In →'}
        </button>
      </form>
      <div className={`mt-6 pt-5 ${dark ? 'border-t border-white/10' : 'border-t border-brand-border'}`}>
        <p className={`text-xs ${dark ? 'text-white/25' : 'text-slate-400'}`}>Powered by AutomatedGuest AI</p>
      </div>
    </>
  )

  return (
    <div className="min-h-screen flex">
      <style>{`
        @keyframes float1{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(20px,-30px) scale(1.05)}}
        @keyframes float2{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(-15px,20px) scale(0.95)}}
        @keyframes float3{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(25px,15px) scale(1.08)}}
        .blob1{animation:float1 8s ease-in-out infinite}
        .blob2{animation:float2 10s ease-in-out infinite}
        .blob3{animation:float3 6s ease-in-out infinite}
      `}</style>

      {/* ── MOBILE ONLY — full white page ── */}
      <div className="flex flex-col w-full lg:hidden min-h-screen" style={{ background: 'linear-gradient(160deg, #0A1628 0%, #0d1f3c 40%, #f5f8ff 40%)' }}>
        {/* Navy top section */}
        <div className="px-6 pt-10 pb-6">
          <div className="flex items-center gap-3 mb-1">
            <img src="/logo.png" alt="AutomatedGuest AI" className="h-10 w-auto" />
            <div>
              <p className="text-white font-bold text-sm">AutomatedGuest AI</p>
              <p className="text-white/40 text-[10px]">AI for Hotels &amp; Resorts</p>
            </div>
          </div>
        </div>

        {/* White card with form */}
        <div className="flex-1 bg-white rounded-t-3xl px-6 pt-8 pb-10 shadow-xl">
          <div className="flex gap-2 mb-6 flex-wrap">
            {['24/7 AI Calls','Live Booking','WhatsApp Alerts'].map(f => (
              <span key={f} className="text-[10px] font-semibold px-2.5 py-1 rounded-full text-brand-blue bg-brand-bluesoft border border-brand-blue/20">{f}</span>
            ))}
          </div>
          <FormContent dark={false} />
        </div>
      </div>

      {/* ── DESKTOP — left white + right dark ── */}
      {/* Left */}
      <div className="hidden lg:flex lg:w-5/12 xl:w-1/2 relative overflow-hidden bg-white flex-col justify-between p-12">
        <div className="blob1 absolute -top-20 -left-20 w-72 h-72 rounded-full opacity-10"
          style={{ background: 'radial-gradient(circle, #2B7FFF, transparent 70%)' }} />
        <div className="blob2 absolute bottom-20 -right-16 w-96 h-96 rounded-full opacity-8"
          style={{ background: 'radial-gradient(circle, #2B7FFF, transparent 70%)' }} />
        <div className="blob3 absolute top-1/2 left-1/3 w-48 h-48 rounded-full opacity-6"
          style={{ background: 'radial-gradient(circle, #0A1628, transparent 70%)' }} />

        <p className="relative text-sm text-slate-400 tracking-wide">AI receptionist for hotels — every call answered, day and night.</p>

        <div className="relative">
          <div className="mb-8 flex justify-start">
            <img src="/logo.png" alt="AutomatedGuest AI" className="h-20 w-auto" />
          </div>
          <h1 className="text-4xl xl:text-5xl font-light leading-tight tracking-tight text-slate-700">
            Your front desk,<br />
            <span className="font-bold text-brand-dark">never sleeps.</span>
          </h1>
          <div className="flex flex-wrap gap-2 mt-6">
            {['24/7 AI Calls','Multilingual','Live Booking','WhatsApp Alerts'].map(f => (
              <span key={f} className="text-xs font-medium px-3 py-1.5 rounded-full bg-brand-bluesoft text-brand-blue border border-brand-blue/20">{f}</span>
            ))}
          </div>
          <div className="mt-8 w-72 rounded-2xl border border-brand-border bg-brand-soft p-5 shadow-sm">
            <p className="text-[10px] text-slate-400 uppercase tracking-widest font-medium">This week</p>
            <p className="text-3xl font-bold mt-1 text-brand-dark">42 calls</p>
            <div className="flex items-end gap-1.5 h-12 mt-4">
              {[40,65,30,80,55,90,70].map((h,i) => <SparkBar key={i} h={h} />)}
            </div>
            <div className="flex items-center gap-1.5 mt-3">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <p className="text-xs text-slate-400">14 bookings · 0 missed</p>
            </div>
          </div>
        </div>

        <div className="relative flex items-center gap-2.5">
          <img src="/logo.png" alt="" className="h-6 w-auto opacity-60" />
          <span className="text-xs text-slate-400 tracking-wide">AutomatedGuest AI Clients Portal</span>
        </div>
      </div>

      {/* Right — dark */}
      <div className="hidden lg:flex lg:w-7/12 xl:w-1/2 flex-col relative overflow-hidden"
        style={{ background: 'linear-gradient(135deg, #0A1628 0%, #0d1f3c 60%, #0a1a32 100%)' }}>
        <div className="absolute top-0 right-0 w-80 h-80 rounded-full opacity-10 pointer-events-none"
          style={{ background: 'radial-gradient(circle, #2B7FFF, transparent 70%)', transform: 'translate(30%, -30%)' }} />
        <div className="flex-1 flex items-center justify-center px-6 py-12 relative z-10">
          <div className="w-full max-w-sm">
            <FormContent dark={true} />
          </div>
        </div>
        <div className="px-8 py-5 flex items-center justify-between text-xs text-white/15 relative z-10">
          <span>© 2026 AutomatedGuest AI</span>
          <span>Clients Portal</span>
        </div>
      </div>
    </div>
  )
}
