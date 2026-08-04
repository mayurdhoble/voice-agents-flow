import { useState } from 'react'
import { api } from '../lib/api'

export default function Settings() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess(false)

    if (next !== confirm) {
      setError('New passwords do not match.')
      return
    }
    if (next.length < 6) {
      setError('New password must be at least 6 characters.')
      return
    }

    setLoading(true)
    try {
      await api('/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: next }),
      })
      setSuccess(true)
      setCurrent('')
      setNext('')
      setConfirm('')
    } catch (err) {
      setError(err.message || 'Failed to change password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-lg">
      <h1 className="text-xl font-semibold text-gray-900 mb-1">Settings</h1>
      <p className="text-sm text-gray-500 mb-8">Manage your portal credentials.</p>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-5">Change Password</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">
              Current Password
            </label>
            <input
              type="password"
              value={current}
              onChange={e => setCurrent(e.target.value)}
              required
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-dark/20 focus:border-brand-dark"
              placeholder="Enter current password"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">
              New Password
            </label>
            <input
              type="password"
              value={next}
              onChange={e => setNext(e.target.value)}
              required
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-dark/20 focus:border-brand-dark"
              placeholder="At least 6 characters"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">
              Confirm New Password
            </label>
            <input
              type="password"
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              required
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-dark/20 focus:border-brand-dark"
              placeholder="Repeat new password"
            />
          </div>

          {error && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          {success && (
            <p className="text-xs text-green-700 bg-green-50 border border-green-100 rounded-lg px-3 py-2">
              Password changed successfully.
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 px-4 bg-brand-dark text-white text-sm font-medium rounded-lg hover:bg-brand-dark/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Saving…' : 'Update Password'}
          </button>
        </form>
      </div>
    </div>
  )
}
