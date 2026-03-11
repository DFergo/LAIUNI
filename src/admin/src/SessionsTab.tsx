import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { listSessions, getSession, toggleSessionFlag, type SessionSummary, type SessionDetail } from './api'

type Filter = 'all' | 'active' | 'completed' | 'flagged'

function timeAgo(iso: string | null): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    active: 'bg-green-50 text-green-700',
    completed: 'bg-gray-100 text-gray-600',
    flagged: 'bg-red-50 text-uni-red',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors[status] || 'bg-gray-100 text-gray-500'}`}>
      {status}
    </span>
  )
}

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

  const filtered = sessions.filter(s => {
    if (filter === 'all') return true
    if (filter === 'active') return s.status === 'active'
    if (filter === 'completed') return s.status === 'completed'
    if (filter === 'flagged') return s.flagged
    return true
  })

  const counts = {
    all: sessions.length,
    active: sessions.filter(s => s.status === 'active').length,
    completed: sessions.filter(s => s.status === 'completed').length,
    flagged: sessions.filter(s => s.flagged).length,
  }

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
          {statusBadge(selected.status)}
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

        {/* Session metadata */}
        <div className="flex gap-4 text-xs text-gray-400">
          <span>Language: {selected.language}</span>
          {selected.created_at && <span>Created: {timeAgo(selected.created_at)}</span>}
          {selected.last_activity && <span>Last activity: {timeAgo(selected.last_activity)}</span>}
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
              <div className="flex justify-between text-xs font-medium text-gray-400 mb-1">
                <span>{msg.role === 'user' ? 'User' : 'Assistant'}</span>
                {msg.timestamp && <span>{timeAgo(msg.timestamp)}</span>}
              </div>
              {msg.role === 'user' ? (
                <div className="whitespace-pre-wrap text-gray-700">{msg.content}</div>
              ) : (
                <div className="prose prose-sm max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-li:text-gray-700 prose-strong:text-gray-800">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              )}
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
          {(['all', 'active', 'completed', 'flagged'] as Filter[]).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                filter === f
                  ? 'bg-uni-blue text-white'
                  : 'bg-white border border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)} ({counts[f]})
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
            {filter === 'flagged' ? 'No flagged sessions' :
             filter === 'completed' ? 'No completed sessions' :
             filter === 'active' ? 'No active sessions' :
             'No sessions. Start a conversation on a frontend to see sessions here.'}
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-md border border-gray-200 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Token</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Frontend</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Company</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Role</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Mode</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Status</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Msgs</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Last Activity</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Flag</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(s => (
                <tr key={s.token} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-gray-800 whitespace-nowrap">{s.token}</td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap text-xs">{s.frontend_name || '—'}</td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{s.company || '—'}</td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{s.role}</td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{s.mode}</td>
                  <td className="px-4 py-3 whitespace-nowrap">{statusBadge(s.status)}</td>
                  <td className="px-4 py-3 text-right text-gray-600">{s.message_count}</td>
                  <td className="px-4 py-3 text-right text-gray-400 text-xs whitespace-nowrap">{timeAgo(s.last_activity)}</td>
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
                  <td className="px-4 py-3 text-right whitespace-nowrap">
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
