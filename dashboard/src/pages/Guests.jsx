import { useEffect, useState, useCallback } from 'react'
import Pagination from '../components/Pagination'

export default function Guests() {
  const [guests, setGuests] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)

  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput)
      setPage(1)
    }, 400)
    return () => clearTimeout(t)
  }, [searchInput])

  const fetchGuests = useCallback(() => {
    const params = new URLSearchParams({ page, limit: 20 })
    if (search) params.set('search', search)

    fetch(`/api/guests?${params}`)
      .then(r => r.json())
      .then(d => {
        setGuests(d.data || [])
        setTotal(d.total || 0)
        setPages(d.pages || 1)
      })
      .catch(console.error)
  }, [page, search])

  useEffect(() => {
    fetchGuests()
  }, [fetchGuests])

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Guests</h1>
        <p className="text-sm text-gray-500 mt-0.5">{total} guest profiles</p>
      </div>

      <div className="flex gap-3 mb-5">
        <input
          type="text"
          placeholder="Search by name…"
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          className="border border-gray-200 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 w-64"
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left">
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Name</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Phone</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Email</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Djubo Tracker</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">First Seen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {guests.length === 0 && (
                <tr><td colSpan={5} className="px-6 py-10 text-center text-gray-400">No guests found</td></tr>
              )}
              {guests.map(g => (
                <tr key={g.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-3 font-medium text-gray-800">{g.name || '—'}</td>
                  <td className="px-6 py-3 text-gray-600">{g.phone || '—'}</td>
                  <td className="px-6 py-3 text-gray-600">{g.email || '—'}</td>
                  <td className="px-6 py-3 text-xs text-gray-500 font-mono">{g.djubo_tracker_id || '—'}</td>
                  <td className="px-6 py-3 text-gray-500 whitespace-nowrap">
                    {g.created_at ? new Date(g.created_at).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={page} pages={pages} onPage={setPage} />
      </div>
    </div>
  )
}
