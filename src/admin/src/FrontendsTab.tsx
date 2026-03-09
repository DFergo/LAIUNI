import { useState, useEffect } from 'react'
import { listFrontends, registerFrontend, updateFrontend, removeFrontend, type Frontend } from './api'

export default function FrontendsTab() {
  const [frontends, setFrontends] = useState<Frontend[]>([])
  const [newUrl, setNewUrl] = useState('')
  const [newName, setNewName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const refresh = async () => {
    try {
      const { frontends: list } = await listFrontends()
      setFrontends(list)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    }
  }

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 10000)
    return () => clearInterval(interval)
  }, [])

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await registerFrontend(newUrl, newName)
      setNewUrl('')
      setNewName('')
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  const handleToggle = async (f: Frontend) => {
    await updateFrontend(f.id, { enabled: !f.enabled })
    await refresh()
  }

  const handleRemove = async (f: Frontend) => {
    await removeFrontend(f.id)
    await refresh()
  }

  const statusColor = (s: string) => {
    if (s === 'online') return 'bg-green-500'
    if (s === 'offline') return 'bg-red-500'
    return 'bg-gray-400'
  }

  return (
    <div className="space-y-6">
      {/* Register form */}
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Add Frontend</h3>
        <form onSubmit={handleRegister} className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
            <input
              type="text"
              value={newUrl}
              onChange={e => setNewUrl(e.target.value)}
              placeholder="http://10.210.66.103:8091"
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none text-sm"
              required
            />
          </div>
          <div className="w-40">
            <label className="block text-sm font-medium text-gray-700 mb-1">Name (optional)</label>
            <input
              type="text"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              placeholder="Worker #1"
              className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="bg-uni-blue text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors hover:opacity-90 disabled:opacity-50"
          >
            {loading ? '...' : 'Register'}
          </button>
        </form>
        {error && <p className="text-uni-red text-sm mt-2">{error}</p>}
      </div>

      {/* Frontends list */}
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Registered Frontends</h3>
        {frontends.length === 0 ? (
          <p className="text-gray-400 text-sm">No frontends registered yet.</p>
        ) : (
          <div className="space-y-3">
            {frontends.map(f => (
              <div key={f.id} className="flex items-center justify-between border border-gray-200 rounded-lg px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className={`w-2.5 h-2.5 rounded-full ${statusColor(f.status)}`} />
                  <div>
                    <div className="text-sm font-medium text-gray-800">{f.name}</div>
                    <div className="text-xs text-gray-400">{f.url} — {f.frontend_type}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleToggle(f)}
                    className={`text-xs px-3 py-1 rounded-lg border font-medium transition-colors ${
                      f.enabled
                        ? 'border-green-300 text-green-700 hover:bg-green-50'
                        : 'border-gray-300 text-gray-500 hover:bg-gray-50'
                    }`}
                  >
                    {f.enabled ? 'Enabled' : 'Disabled'}
                  </button>
                  <button
                    onClick={() => handleRemove(f)}
                    className="text-xs px-3 py-1 rounded-lg border border-uni-red text-uni-red hover:bg-red-50 font-medium transition-colors"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
