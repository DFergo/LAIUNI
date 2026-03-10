import { useState, useEffect } from 'react'
import { listSessions, getSession, toggleSessionFlag, type SessionSummary, type SessionDetail } from './api'

type Filter = 'all' | 'flagged'

export default function SessionsTab() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [filter, setFilter] = useState<Filter>('all')
  const [selected, setSelected] = useState<SessionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = async () => {
    try {
      const data = await listSessions()
      setSessions(data.sessions)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sessions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 10000)
    return () => clearInterval(interval)
  }, [])

  const viewSession = async (token: string) => {
    setError('')
    try {
      const detail = await getSession(token)
      setSelected(detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load session')
    }
  }

  const handleFlag = async (token: string) => {
    try {
      const result = await toggleSessionFlag(token)
      setSessions(prev => prev.map(s =>
        s.token === token ? { ...s, flagged: result.flagged } : s
      ))
      if (selected?.token === token) {
        setSelected({ ...selected, flagged: result.flagged })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle flag')
    }
  }

  const filtered = filter === 'flagged'
    ? sessions.filter(s => s.flagged)
    : sessions

  if (loading) return <p className="text-gray-400 text-sm">Loading...</p>

  // Detail view
  if (selected) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSelected(null)}
            className="text-sm text-uni-blue hover:underline"
          >
            &larr; Back to list
          </button>
          <span className="font-mono text-lg font-semibold text-gray-800">{selected.token}</span>
          <button
            onClick={() => handleFlag(selected.token)}
            className={`text-xs px-2 py-1 rounded-lg border transition-colors ${
              selected.flagged
                ? 'border-uni-red text-uni-red hover:bg-red-50'
                : 'border-gray-300 text-gray-500 hover:bg-gray-50'
            }`}
          >
            {selected.flagged ? 'Unflag' : 'Flag'}
          </button>
        </div>

        {/* Survey info */}
        {Object.keys(selected.survey).length > 0 && (
          <div className="bg-white rounded-xl shadow-md border border-gray-200 p-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-2">Survey</h4>
            <div className="grid grid-cols-2 gap-2 text-sm">
              {Object.entries(selected.survey).map(([key, val]) => (
                <div key={key}>
                  <span className="text-gray-400">{key}: </span>
                  <span className="text-gray-700">{String(val)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Conversation */}
        <div className="bg-white rounded-xl shadow-md border border-gray-200 p-4 space-y-3">
          <h4 className="text-sm font-semibold text-gray-700 mb-2">
            Conversation ({selected.messages.length} messages)
          </h4>
          {selected.messages.length === 0 && (
            <p className="text-gray-400 text-sm">No messages yet</p>
          )}
          {selected.messages.map((msg, i) => (
            <div
              key={i}
              className={`rounded-lg px-4 py-3 text-sm ${
                msg.role === 'user'
                  ? 'bg-blue-50 border border-blue-100'
                  : 'bg-gray-50 border border-gray-100'
              }`}
            >
              <div className="text-xs font-medium text-gray-400 mb-1">
                {msg.role === 'user' ? 'User' : 'Assistant'}
              </div>
              <div className="whitespace-pre-wrap text-gray-700">{msg.content}</div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // List view
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {(['all', 'flagged'] as Filter[]).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                filter === f
                  ? 'bg-uni-blue text-white'
                  : 'bg-white border border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {f === 'all' ? `All (${sessions.length})` : `Flagged (${sessions.filter(s => s.flagged).length})`}
            </button>
          ))}
        </div>
        <button
          onClick={refresh}
          className="text-xs px-3 py-1 rounded-lg border border-gray-300 text-gray-500 hover:bg-gray-50 font-medium transition-colors"
        >
          Refresh
        </button>
      </div>

      {error && <p className="text-sm text-uni-red">{error}</p>}

      {filtered.length === 0 ? (
        <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 text-center">
          <p className="text-gray-400 text-sm">
            {filter === 'flagged' ? 'No flagged sessions' : 'No active sessions. Start a conversation on a frontend to see sessions here.'}
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-md border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="text-left px-4 py-3 font-medium text-gray-600">Token</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Role</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Mode</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Messages</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">Flag</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(s => (
                <tr key={s.token} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-gray-800">{s.token}</td>
                  <td className="px-4 py-3 text-gray-600">{s.role}</td>
                  <td className="px-4 py-3 text-gray-600">{s.mode}</td>
                  <td className="px-4 py-3 text-right text-gray-600">{s.message_count}</td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => handleFlag(s.token)}
                      className={`text-xs px-2 py-0.5 rounded transition-colors ${
                        s.flagged
                          ? 'bg-red-50 text-uni-red'
                          : 'text-gray-300 hover:text-gray-500'
                      }`}
                    >
                      {s.flagged ? 'flagged' : 'flag'}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => viewSession(s.token)}
                      className="text-xs text-uni-blue hover:underline"
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
