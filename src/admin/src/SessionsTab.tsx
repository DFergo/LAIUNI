import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  listSessions, getSession, toggleSessionFlag, getSessionDocuments, generateDocument,
  listFrontends, getLifecycleSettings, updateLifecycleSettings,
  purgeFrontendSessions, getResumeWindows, updateResumeWindows,
  archiveSession, restoreSession, deleteSession,
  type SessionSummary, type SessionDetail, type SessionDocuments,
  type Frontend, type LifecycleConfig, type ResumeWindows,
} from './api'

type Filter = 'all' | 'active' | 'completed' | 'flagged'
type SortCol = 'token' | 'frontend_name' | 'company' | 'role' | 'mode' | 'status' | 'message_count' | 'last_activity' | ''

const DOC_LABELS: Record<string, string> = {
  summary: 'User Summary',
  internal_summary: 'Internal Summary',
  report: 'Report',
}

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

function docIndicator(has: boolean) {
  return has
    ? <span className="text-green-600 font-bold" title="Available">&#10003;</span>
    : <span className="text-gray-300" title="Not generated">&#10007;</span>
}

export default function SessionsTab() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [filter, setFilter] = useState<Filter>('all')
  const [selected, setSelected] = useState<SessionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Document state for detail view
  const [docs, setDocs] = useState<SessionDocuments | null>(null)
  const [docsLoading, setDocsLoading] = useState(false)
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null)
  const [generating, setGenerating] = useState<string | null>(null)

  // Lifecycle settings state
  const [showLifecycle, setShowLifecycle] = useState(false)
  const [frontends, setFrontends] = useState<Frontend[]>([])
  const [lifecycleSettings, setLifecycleSettings] = useState<Record<string, LifecycleConfig>>({})
  const [lifecycleDefaults, setLifecycleDefaults] = useState<LifecycleConfig>({
    auto_close_enabled: false, auto_close_hours: 2,
    auto_cleanup_enabled: false, auto_cleanup_days: 30,
  })
  const [selectedFrontend, setSelectedFrontend] = useState('')
  const [lifecycleForm, setLifecycleForm] = useState<LifecycleConfig | null>(null)
  const [lifecycleSaving, setLifecycleSaving] = useState(false)
  const [lifecycleMsg, setLifecycleMsg] = useState('')
  const [resumeWindows, setResumeWindows] = useState<ResumeWindows | null>(null)
  const [resumeMsg, setResumeMsg] = useState('')
  const [purgeMsg, setPurgeMsg] = useState('')

  // Table sort/filter + archived view (Sprint 28)
  const [sortCol, setSortCol] = useState<SortCol>('last_activity')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [colFilters, setColFilters] = useState<{ frontend_name?: string; role?: string; mode?: string; status?: string; token?: string; company?: string }>({})
  const [showArchived, setShowArchived] = useState(false)

  const refresh = async () => {
    try {
      const data = await listSessions(showArchived)
      setSessions(data.sessions)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sessions')
    } finally {
      setLoading(false)
    }
  }

  const loadLifecycle = async () => {
    try {
      const [fData, lcData, rw] = await Promise.all([listFrontends(), getLifecycleSettings(), getResumeWindows()])
      setFrontends(fData.frontends)
      setLifecycleSettings(lcData.settings)
      setLifecycleDefaults(lcData.defaults)
      setResumeWindows(rw)
      // Auto-select first frontend if none selected
      if (!selectedFrontend && fData.frontends.length > 0) {
        const fid = fData.frontends[0].id
        setSelectedFrontend(fid)
        setLifecycleForm({ ...lcData.defaults, ...lcData.settings[fid] })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load lifecycle settings')
    }
  }

  const selectFrontendLifecycle = (fid: string) => {
    setSelectedFrontend(fid)
    setLifecycleForm({ ...lifecycleDefaults, ...lifecycleSettings[fid] })
    setLifecycleMsg('')
  }

  const saveLifecycle = async () => {
    if (!selectedFrontend || !lifecycleForm) return
    setLifecycleSaving(true)
    setLifecycleMsg('')
    try {
      await updateLifecycleSettings(selectedFrontend, lifecycleForm)
      setLifecycleSettings(prev => ({ ...prev, [selectedFrontend]: lifecycleForm }))
      setLifecycleMsg('Saved')
      setTimeout(() => setLifecycleMsg(''), 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setLifecycleSaving(false)
    }
  }

  const handlePurge = async () => {
    if (!selectedFrontend) return
    const feName = frontends.find(f => f.id === selectedFrontend)?.name || selectedFrontend
    if (!confirm(
      `Permanently DELETE from disk all completed/archived sessions for "${feName}"?\n\n` +
      `Active (in-progress) sessions are spared. This removes the case files for good and CANNOT be undone.`
    )) return
    setPurgeMsg('Purging…')
    try {
      const { purged } = await purgeFrontendSessions(selectedFrontend)
      setPurgeMsg(`Purged ${purged} session(s)`)
      setTimeout(() => setPurgeMsg(''), 4000)
      await refresh()
    } catch (err) {
      setPurgeMsg(err instanceof Error ? err.message : 'Purge failed')
    }
  }

  const saveResumeWindows = async () => {
    if (!resumeWindows) return
    setResumeMsg('')
    try {
      const saved = await updateResumeWindows(resumeWindows)
      setResumeWindows(saved)
      setResumeMsg('Saved'); setTimeout(() => setResumeMsg(''), 2000)
    } catch (err) {
      setResumeMsg(err instanceof Error ? err.message : 'Failed to save')
    }
  }

  useEffect(() => {
    if (showLifecycle) loadLifecycle()
  }, [showLifecycle])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 10000)
    return () => clearInterval(interval)
  }, [showArchived])

  const viewSession = async (token: string) => {
    setError('')
    setDocs(null)
    setExpandedDoc(null)
    try {
      const detail = await getSession(token)
      setSelected(detail)
      // Load documents in background
      setDocsLoading(true)
      const docsData = await getSessionDocuments(token)
      setDocs(docsData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load session')
    } finally {
      setDocsLoading(false)
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

  const handleArchive = async (token: string) => {
    setError('')
    try { await archiveSession(token); await refresh() }
    catch (err) { setError(err instanceof Error ? err.message : 'Archive failed') }
  }

  const handleRestore = async (token: string) => {
    setError('')
    try { await restoreSession(token); await refresh() }
    catch (err) { setError(err instanceof Error ? err.message : 'Restore failed') }
  }

  const handleHardDelete = async (token: string) => {
    if (!confirm(`Permanently delete session ${token} from disk? This removes the conversation, report and documents for good and CANNOT be undone.`)) return
    setError('')
    try { await deleteSession(token); await refresh() }
    catch (err) { setError(err instanceof Error ? err.message : 'Delete failed') }
  }

  const handleSort = (col: SortCol) => {
    if (sortCol === col) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortCol(col); setSortDir('asc') }
  }

  const handleGenerate = async (token: string, docType: string) => {
    setGenerating(docType)
    setError('')
    try {
      const result = await generateDocument(token, docType)
      // Update docs state with new content
      setDocs(prev => prev
        ? { ...prev, documents: { ...prev.documents, [docType]: result.content } }
        : { token, documents: { [docType]: result.content } }
      )
      // Update session list doc indicators
      setSessions(prev => prev.map(s =>
        s.token === token ? { ...s, docs: { ...s.docs, [docType]: true } } : s
      ))
      setExpandedDoc(docType)
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to generate ${docType}`)
    } finally {
      setGenerating(null)
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

  const uniqueValues = (key: 'frontend_name' | 'role' | 'mode' | 'status') =>
    Array.from(new Set(sessions.map(s => s[key]).filter(Boolean))).sort()

  const colFiltered = filtered.filter(s => {
    if (colFilters.frontend_name && s.frontend_name !== colFilters.frontend_name) return false
    if (colFilters.role && s.role !== colFilters.role) return false
    if (colFilters.mode && s.mode !== colFilters.mode) return false
    if (colFilters.status && s.status !== colFilters.status) return false
    if (colFilters.token && !s.token.toLowerCase().includes(colFilters.token.toLowerCase())) return false
    if (colFilters.company && !(s.company || '').toLowerCase().includes(colFilters.company.toLowerCase())) return false
    return true
  })

  const displayRows = [...colFiltered].sort((a, b) => {
    if (!sortCol) return 0
    let av: any
    let bv: any
    if (sortCol === 'last_activity') {
      av = a.last_activity ? new Date(a.last_activity).getTime() : 0
      bv = b.last_activity ? new Date(b.last_activity).getTime() : 0
    } else if (sortCol === 'message_count') {
      av = a.message_count ?? 0
      bv = b.message_count ?? 0
    } else {
      av = String(a[sortCol] ?? '').toLowerCase()
      bv = String(b[sortCol] ?? '').toLowerCase()
    }
    if (av < bv) return sortDir === 'asc' ? -1 : 1
    if (av > bv) return sortDir === 'asc' ? 1 : -1
    return 0
  })

  const sortArrow = (col: SortCol) => (sortCol === col ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '')

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

        {/* Documents section */}
        <div className="bg-white rounded-xl shadow-md border border-gray-200 p-4 space-y-3">
          <h4 className="text-sm font-semibold text-gray-700 mb-2">Documents</h4>
          {docsLoading ? (
            <p className="text-gray-400 text-sm">Loading documents...</p>
          ) : (
            <div className="space-y-2">
              {Object.entries(DOC_LABELS).map(([docType, label]) => {
                const content = docs?.documents?.[docType] ?? null
                const hasContent = content !== null && content !== undefined
                const isExpanded = expandedDoc === docType
                const isGenerating = generating === docType

                return (
                  <div key={docType} className="border border-gray-200 rounded-lg">
                    <div className="flex items-center justify-between px-4 py-2">
                      <div className="flex items-center gap-2">
                        {docIndicator(hasContent)}
                        <span className="text-sm font-medium text-gray-700">{label}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {hasContent && (
                          <button
                            onClick={() => setExpandedDoc(isExpanded ? null : docType)}
                            className="text-xs text-uni-blue hover:underline"
                          >
                            {isExpanded ? 'Collapse' : 'View'}
                          </button>
                        )}
                        <button
                          onClick={() => handleGenerate(selected.token, docType)}
                          disabled={isGenerating || generating !== null}
                          className={`text-xs px-3 py-1 rounded-lg border transition-colors ${
                            isGenerating
                              ? 'border-gray-200 text-gray-400 bg-gray-50 cursor-wait'
                              : 'border-uni-blue text-uni-blue hover:bg-blue-50'
                          }`}
                        >
                          {isGenerating ? 'Generating...' : hasContent ? 'Regenerate' : 'Generate'}
                        </button>
                      </div>
                    </div>
                    {isExpanded && hasContent && (
                      <div className="border-t border-gray-200 px-4 py-3">
                        <div className="prose prose-sm max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-li:text-gray-700 prose-strong:text-gray-800">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

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
        <div className="flex gap-2">
          <button
            onClick={() => setShowArchived(v => !v)}
            className={`text-xs px-3 py-1 rounded-lg border transition-colors font-medium ${
              showArchived ? 'border-uni-blue text-uni-blue bg-blue-50' : 'border-gray-300 text-gray-500 hover:bg-gray-50'
            }`}
          >
            {showArchived ? 'Hide archived' : 'Show archived'}
          </button>
          <button
            onClick={() => setShowLifecycle(!showLifecycle)}
            className={`text-xs px-3 py-1 rounded-lg border transition-colors font-medium ${
              showLifecycle ? 'border-uni-blue text-uni-blue bg-blue-50' : 'border-gray-300 text-gray-500 hover:bg-gray-50'
            }`}
          >
            Lifecycle Settings
          </button>
          <button
            onClick={refresh}
            className="text-xs px-3 py-1 rounded-lg border border-gray-300 text-gray-500 hover:bg-gray-50 font-medium transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Lifecycle settings panel */}
      {showLifecycle && (
        <div className="bg-white rounded-xl shadow-md border border-gray-200 p-4 space-y-4">
          <h4 className="text-sm font-semibold text-gray-700">Session Lifecycle Settings</h4>

          {frontends.length === 0 ? (
            <p className="text-gray-400 text-sm">No frontends registered. Register a frontend first.</p>
          ) : (
            <>
              {/* Frontend selector */}
              <div className="flex gap-2 flex-wrap">
                {frontends.map(f => (
                  <button
                    key={f.id}
                    onClick={() => selectFrontendLifecycle(f.id)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      selectedFrontend === f.id
                        ? 'bg-uni-blue text-white'
                        : 'bg-white border border-gray-300 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    {f.name || f.url}
                  </button>
                ))}
              </div>

              {lifecycleForm && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Auto-close */}
                  <div className="border border-gray-200 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-700">Auto-close inactive sessions</span>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={lifecycleForm.auto_close_enabled}
                          onChange={e => setLifecycleForm({ ...lifecycleForm, auto_close_enabled: e.target.checked })}
                          className="sr-only peer"
                        />
                        <div className="w-9 h-5 bg-gray-200 peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-uni-blue"></div>
                      </label>
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-gray-500">Timeout:</label>
                      <input
                        type="number"
                        min={1}
                        max={48}
                        value={lifecycleForm.auto_close_hours}
                        onChange={e => setLifecycleForm({ ...lifecycleForm, auto_close_hours: parseInt(e.target.value) || 2 })}
                        disabled={!lifecycleForm.auto_close_enabled}
                        className="w-16 px-2 py-1 text-sm border border-gray-300 rounded disabled:opacity-50"
                      />
                      <span className="text-xs text-gray-500">hours</span>
                    </div>
                    <p className="text-xs text-gray-400">
                      Generates summary, internal summary, and report automatically when session has no activity.
                    </p>
                  </div>

                  {/* Auto-cleanup */}
                  <div className="border border-gray-200 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-700">Auto-cleanup old sessions</span>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={lifecycleForm.auto_cleanup_enabled}
                          onChange={e => setLifecycleForm({ ...lifecycleForm, auto_cleanup_enabled: e.target.checked })}
                          className="sr-only peer"
                        />
                        <div className="w-9 h-5 bg-gray-200 peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-uni-blue"></div>
                      </label>
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-gray-500">Retention:</label>
                      <input
                        type="number"
                        min={1}
                        max={365}
                        value={lifecycleForm.auto_cleanup_days}
                        onChange={e => setLifecycleForm({ ...lifecycleForm, auto_cleanup_days: parseInt(e.target.value) || 30 })}
                        disabled={!lifecycleForm.auto_cleanup_enabled}
                        className="w-16 px-2 py-1 text-sm border border-gray-300 rounded disabled:opacity-50"
                      />
                      <span className="text-xs text-gray-500">days</span>
                    </div>
                    <p className="text-xs text-gray-400">
                      Removes completed sessions from the listing. Files on disk are preserved.
                    </p>
                  </div>
                </div>
              )}

              <div className="flex items-center gap-3">
                <button
                  onClick={saveLifecycle}
                  disabled={lifecycleSaving}
                  className="px-4 py-1.5 bg-uni-blue text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                >
                  {lifecycleSaving ? 'Saving...' : 'Save'}
                </button>
                {lifecycleMsg && <span className="text-xs text-green-600 font-medium">{lifecycleMsg}</span>}
                <div className="flex-1" />
                <button
                  onClick={handlePurge}
                  className="px-3 py-1.5 border border-uni-red text-uni-red text-sm font-medium rounded-lg hover:bg-red-50 transition-colors"
                  title="Permanently delete this frontend's completed/archived session files from disk"
                >
                  Purge sessions
                </button>
                {purgeMsg && <span className="text-xs text-gray-600">{purgeMsg}</span>}
              </div>
            </>
          )}

          {/* Per-profile resume window (global; distinct from auto-close) */}
          {resumeWindows && (
            <div className="border-t border-gray-200 pt-4">
              <div className="text-sm font-medium text-gray-700 mb-1">Session resume window (per profile)</div>
              <p className="text-xs text-gray-400 mb-3">How long a user can resume a session by token. Independent of auto-close. Applies to all frontends.</p>
              <div className="flex flex-wrap items-end gap-3">
                {(['worker', 'representative', 'organizer', 'officer'] as const).map(role => (
                  <div key={role}>
                    <label className="block text-xs text-gray-500 mb-1 capitalize">{role}</label>
                    <div className="flex items-center gap-1">
                      <input
                        type="number" min={1} max={1000}
                        value={resumeWindows[role]}
                        onChange={e => setResumeWindows({ ...resumeWindows, [role]: parseInt(e.target.value) || 0 })}
                        className="w-20 px-2 py-1 text-sm border border-gray-300 rounded"
                      />
                      <span className="text-xs text-gray-500">h</span>
                    </div>
                  </div>
                ))}
                <button onClick={saveResumeWindows} className="px-4 py-1.5 bg-uni-blue text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors">Save</button>
                {resumeMsg && <span className="text-xs text-green-600 font-medium">{resumeMsg}</span>}
              </div>
            </div>
          )}
        </div>
      )}

      {error && <p className="text-sm text-uni-red">{error}</p>}

      {displayRows.length === 0 ? (
        <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 text-center">
          <p className="text-gray-400 text-sm">
            {sessions.length === 0
              ? 'No sessions. Start a conversation on a frontend to see sessions here.'
              : 'No sessions match the current filters.'}
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-md border border-gray-200 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                {([['token', 'Token'], ['frontend_name', 'Frontend'], ['company', 'Company'], ['role', 'Role'], ['mode', 'Mode'], ['status', 'Status']] as [SortCol, string][]).map(([col, label]) => (
                  <th key={col} className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">
                    <button onClick={() => handleSort(col)} className="flex items-center hover:text-gray-900">
                      {label}<span className="text-uni-blue">{sortArrow(col)}</span>
                    </button>
                  </th>
                ))}
                <th className="text-center px-3 py-3 font-medium text-gray-600 whitespace-nowrap" title="User Summary">Sum</th>
                <th className="text-center px-3 py-3 font-medium text-gray-600 whitespace-nowrap" title="Internal Summary">Int</th>
                <th className="text-center px-3 py-3 font-medium text-gray-600 whitespace-nowrap" title="Report">Rep</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600 whitespace-nowrap">
                  <button onClick={() => handleSort('message_count')} className="hover:text-gray-900">Msgs<span className="text-uni-blue">{sortArrow('message_count')}</span></button>
                </th>
                <th className="text-right px-4 py-3 font-medium text-gray-600 whitespace-nowrap">
                  <button onClick={() => handleSort('last_activity')} className="hover:text-gray-900">Last Activity<span className="text-uni-blue">{sortArrow('last_activity')}</span></button>
                </th>
                <th className="text-center px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Flag</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600"></th>
              </tr>
              <tr className="border-b border-gray-200 bg-white">
                <th className="px-2 py-2">
                  <input value={colFilters.token || ''} onChange={e => setColFilters(f => ({ ...f, token: e.target.value }))} placeholder="filter" className="w-24 px-2 py-1 text-xs font-normal border border-gray-200 rounded" />
                </th>
                <th className="px-2 py-2">
                  <select value={colFilters.frontend_name || ''} onChange={e => setColFilters(f => ({ ...f, frontend_name: e.target.value || undefined }))} className="px-1 py-1 text-xs font-normal border border-gray-200 rounded">
                    <option value="">All</option>
                    {uniqueValues('frontend_name').map(v => <option key={v} value={v}>{v}</option>)}
                  </select>
                </th>
                <th className="px-2 py-2">
                  <input value={colFilters.company || ''} onChange={e => setColFilters(f => ({ ...f, company: e.target.value }))} placeholder="filter" className="w-24 px-2 py-1 text-xs font-normal border border-gray-200 rounded" />
                </th>
                <th className="px-2 py-2">
                  <select value={colFilters.role || ''} onChange={e => setColFilters(f => ({ ...f, role: e.target.value || undefined }))} className="px-1 py-1 text-xs font-normal border border-gray-200 rounded">
                    <option value="">All</option>
                    {uniqueValues('role').map(v => <option key={v} value={v}>{v}</option>)}
                  </select>
                </th>
                <th className="px-2 py-2">
                  <select value={colFilters.mode || ''} onChange={e => setColFilters(f => ({ ...f, mode: e.target.value || undefined }))} className="px-1 py-1 text-xs font-normal border border-gray-200 rounded">
                    <option value="">All</option>
                    {uniqueValues('mode').map(v => <option key={v} value={v}>{v}</option>)}
                  </select>
                </th>
                <th className="px-2 py-2">
                  <select value={colFilters.status || ''} onChange={e => setColFilters(f => ({ ...f, status: e.target.value || undefined }))} className="px-1 py-1 text-xs font-normal border border-gray-200 rounded">
                    <option value="">All</option>
                    {uniqueValues('status').map(v => <option key={v} value={v}>{v}</option>)}
                  </select>
                </th>
                <th colSpan={7}></th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map(s => (
                <tr key={s.token} className={`border-b border-gray-100 hover:bg-gray-50 ${s.archived ? 'opacity-60' : ''}`}>
                  <td className="px-4 py-3 font-mono text-gray-800 whitespace-nowrap">
                    {s.token}
                    {s.archived && <span className="ml-2 text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">archived</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap text-xs">{s.frontend_name || '—'}</td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{s.company || '—'}</td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{s.role}</td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{s.mode}</td>
                  <td className="px-4 py-3 whitespace-nowrap">{statusBadge(s.status)}</td>
                  <td className="px-3 py-3 text-center">{docIndicator(s.docs?.summary ?? false)}</td>
                  <td className="px-3 py-3 text-center">{docIndicator(s.docs?.internal_summary ?? false)}</td>
                  <td className="px-3 py-3 text-center">{docIndicator(s.docs?.report ?? false)}</td>
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
                    <div className="flex items-center gap-3 justify-end">
                      <button onClick={() => viewSession(s.token)} className="text-xs text-uni-blue hover:underline">View</button>
                      {s.archived
                        ? <button onClick={() => handleRestore(s.token)} className="text-xs text-gray-500 hover:underline">Restore</button>
                        : <button onClick={() => handleArchive(s.token)} className="text-xs text-gray-500 hover:underline">Archive</button>}
                      <button onClick={() => handleHardDelete(s.token)} className="text-xs text-uni-red hover:underline">Delete</button>
                    </div>
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
