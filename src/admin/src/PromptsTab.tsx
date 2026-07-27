import { useState, useEffect } from 'react'
import {
  listPrompts, readPrompt, savePrompt,
  getPromptSource, setPromptSource, resetPrompts,
  listFrontends, getFrontendConfig,
  listModules, getFrontendModules, setFrontendModules,
  type PromptFile, type Frontend, type FrontendConfig, type ModuleInfo
} from './api'

// Sprint 23 scoping: map a prompt filename to the profile/mode it belongs to.
// Role/mode-specific prompts are shown only when active on the frontend; all
// other (shared) prompts are always shown.
const MODE_TO_SUFFIX: Record<string, string> = {
  documentation: 'document', interview: 'interview', advisory: 'advisory', submit: 'submit', training: 'training',
}
const WIRED_MODES: Record<string, string[]> = {
  organizer: ['documentation', 'interview', 'advisory', 'submit'],
  officer: ['documentation', 'interview', 'advisory', 'submit', 'training'],
}

function promptVisible(name: string, cfg: FrontendConfig | null): boolean {
  if (!cfg) return true
  const profiles = cfg.profiles || []
  const activeSuffixes = (role: string): string[] => {
    const m = (cfg.modes?.[role] && cfg.modes[role].length > 0) ? cfg.modes[role] : (WIRED_MODES[role] || [])
    return m.map(mode => MODE_TO_SUFFIX[mode]).filter(Boolean)
  }
  const base = name.replace(/\.md$/, '')

  if (base === 'worker') return profiles.includes('worker')
  if (base === 'worker_representative') return profiles.includes('representative')
  for (const role of ['organizer', 'officer']) {
    if (base.startsWith(role + '_')) {
      if (!profiles.includes(role)) return false
      return activeSuffixes(role).includes(base.slice(role.length + 1))
    }
  }
  const ss = base.match(/^session_summary_(worker|representative|organizer|officer)$/)
  if (ss) return profiles.includes(ss[1])

  return true  // shared prompts (core, context_template, evidence_summary, …)
}

type ResetSource = 'global' | 'factory'

export default function PromptsTab() {
  const [categories, setCategories] = useState<Record<string, PromptFile[]>>({})
  const [selected, setSelected] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [originalContent, setOriginalContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(true)

  // Sprint 32: scope = 'global' or a frontend id. Per-frontend Global/Custom flag.
  const [scope, setScope] = useState<string>('global')
  const [frontends, setFrontends] = useState<Frontend[]>([])
  const [feConfig, setFeConfig] = useState<FrontendConfig | null>(null)
  const [useGlobal, setUseGlobal] = useState(true)

  // Feature modules (per-frontend, only when decoupled)
  const [modules, setModules] = useState<ModuleInfo[]>([])
  const [enabledModules, setEnabledModules] = useState<string[]>([])

  // Reset modal: which prompts to reset + the source (global vs factory)
  const [resetModal, setResetModal] = useState<{ source: ResetSource } | null>(null)
  const [resetSelection, setResetSelection] = useState<Set<string>>(new Set())

  const frontendId = scope === 'global' ? undefined : scope
  const isFrontend = !!frontendId
  const readOnly = isFrontend && useGlobal

  useEffect(() => { loadInitial() }, [])

  const loadInitial = async () => {
    try {
      const [feData, modData] = await Promise.all([listFrontends(), listModules()])
      setFrontends(feData.frontends)
      setModules(modData.available)
      await loadScope('global')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  const loadScope = async (sc: string) => {
    setError(''); setSuccess('')
    setSelected(null); setContent(''); setOriginalContent('')
    const fid = sc === 'global' ? undefined : sc
    if (fid) {
      try { const { config } = await getFrontendConfig(fid); setFeConfig(config) } catch { setFeConfig(null) }
      try { const s = await getPromptSource(fid); setUseGlobal(s.use_global) } catch { setUseGlobal(true) }
      try { const m = await getFrontendModules(fid); setEnabledModules(m.enabled) } catch { setEnabledModules([]) }
    } else {
      setFeConfig(null); setUseGlobal(true); setEnabledModules([])
    }
    try {
      const data = await listPrompts(fid)
      setCategories(data.categories)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load prompts')
    }
  }

  const handleScopeChange = async (sc: string) => { setScope(sc); await loadScope(sc) }

  const selectPrompt = async (name: string) => {
    setError(''); setSuccess('')
    try {
      const data = await readPrompt(name, frontendId)
      setSelected(name)
      setContent(data.content)
      setOriginalContent(data.content)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load prompt')
    }
  }

  const handleSave = async () => {
    if (!selected || readOnly) return
    setSaving(true); setError(''); setSuccess('')
    try {
      await savePrompt(selected, content, frontendId)
      setOriginalContent(content)
      setSuccess('Saved')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const toggleUseGlobal = async () => {
    if (!frontendId) return
    const next = !useGlobal
    if (next && enabledModules.length > 0) {
      if (!confirm(
        `Re-coupling this frontend to the global prompt set will DISABLE its active module(s) (${enabledModules.join(', ')}) and remove their files from this frontend's RAG.\n\n` +
        `Its custom prompt files are kept on disk but stop applying. Continue?`
      )) return
    }
    setError(''); setSuccess('')
    try {
      const res = await setPromptSource(frontendId, next)
      setUseGlobal(res.use_global)
      if (res.modules_deactivated.length > 0) setEnabledModules([])
      setSuccess(next ? 'Now using the global prompt set.' : 'Decoupled — this frontend now uses its own custom prompts.')
      setTimeout(() => setSuccess(''), 4000)
      await loadScope(scope)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change prompt source')
    }
  }

  const toggleModule = async (mid: string) => {
    if (!frontendId || readOnly) return
    const on = enabledModules.includes(mid)
    const mod = modules.find(m => m.id === mid)
    const next = on ? enabledModules.filter(m => m !== mid) : [...enabledModules, mid]
    if (!on) {
      if (!confirm(`Activate module "${mod?.name || mid}"? Its ${mod?.doc_count ?? 0} reference file(s) will be added to this frontend's RAG (they cannot be deleted from the RAG panel until the module is disabled).`)) return
    } else {
      if (!confirm(`Disable module "${mod?.name || mid}"? Its ${mod?.doc_count ?? 0} file(s) will be removed from this frontend's RAG.`)) return
    }
    setError(''); setSuccess('')
    try {
      const res = await setFrontendModules(frontendId, next)
      setEnabledModules(res.enabled)
      setSuccess(on ? 'Module disabled.' : 'Module activated — files added to RAG.')
      setTimeout(() => setSuccess(''), 4000)
      // Re-read the current prompt: module slots may now render differently.
      if (selected) await selectPrompt(selected)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle module')
    }
  }

  // --- Reset modal ---
  const openReset = (source: ResetSource) => {
    setResetSelection(new Set())  // empty = interpreted as "all" on confirm unless user picks
    setResetModal({ source })
  }

  const confirmReset = async () => {
    if (!resetModal) return
    const names = resetSelection.size > 0 ? Array.from(resetSelection) : ['all']
    setError(''); setSuccess('')
    try {
      const res = await resetPrompts({
        frontendId,
        toFactory: !isFrontend || resetModal.source === 'factory',
        names,
      })
      setResetModal(null)
      setSuccess(`Reset ${res.reset.length} prompt(s).`)
      setTimeout(() => setSuccess(''), 4000)
      await loadScope(scope)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed')
    }
  }

  const formatDate = (ts: number | null) => (ts ? new Date(ts * 1000).toLocaleString() : '—')
  const dirty = content !== originalContent

  const visibleCategories = Object.entries(categories)
    .map(([cat, files]) => [cat, files.filter(f => promptVisible(f.name, feConfig))] as [string, PromptFile[]])
    .filter(([, files]) => files.length > 0)

  const allVisibleNames = visibleCategories.flatMap(([, files]) => files.map(f => f.name))

  if (loading) return <p className="text-gray-400 text-sm">Loading...</p>

  return (
    <div className="space-y-4">
      {/* Scope selector + source flag + reset buttons */}
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-gray-700">Scope:</span>
            <select
              value={scope}
              onChange={e => handleScopeChange(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
            >
              <option value="global">Global (shared default)</option>
              {frontends.map(fe => <option key={fe.id} value={fe.id}>{fe.name || fe.id}</option>)}
            </select>

            {isFrontend && (
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer ml-2">
                <input type="checkbox" checked={useGlobal} onChange={toggleUseGlobal} className="rounded" />
                Use global prompt set
              </label>
            )}
          </div>

          <div className="flex items-center gap-2">
            {isFrontend && (
              <button onClick={() => openReset('global')} className="border border-gray-300 text-gray-600 rounded-lg px-3 py-1.5 text-xs font-medium hover:bg-gray-50">
                Reset from global…
              </button>
            )}
            <button onClick={() => openReset('factory')} className="border border-gray-300 text-gray-600 rounded-lg px-3 py-1.5 text-xs font-medium hover:bg-gray-50">
              Reset from factory…
            </button>
          </div>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          {!isFrontend
            ? 'The shared global prompt set. Frontends coupled to global serve these prompts.'
            : useGlobal
              ? 'This frontend serves the GLOBAL prompt set. Its own prompts are shown read-only — untick "Use global prompt set" to edit and to enable modules.'
              : 'This frontend serves its OWN custom prompts. Edits here apply only to this frontend.'}
        </p>
      </div>

      {/* Feature modules (frontend scope only) */}
      {isFrontend && (
        <div className={`bg-white rounded-xl shadow-md border border-gray-200 p-4 ${readOnly ? 'opacity-60' : ''}`}>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-gray-700">Feature Modules</h4>
            {readOnly && <span className="text-xs text-gray-400">Decouple from global to enable</span>}
          </div>
          {modules.length === 0 ? (
            <p className="text-xs text-gray-400">No modules available.</p>
          ) : (
            <div className="space-y-2">
              {modules.map(m => (
                <label key={m.id} className={`flex items-center gap-2 text-sm ${readOnly ? 'cursor-not-allowed text-gray-400' : 'text-gray-700 cursor-pointer'}`}>
                  <input
                    type="checkbox"
                    checked={enabledModules.includes(m.id)}
                    disabled={readOnly}
                    onChange={() => toggleModule(m.id)}
                    className="rounded"
                  />
                  <span className="font-medium">{m.name}</span>
                  <span className="text-xs text-gray-400">· {m.doc_count} RAG file(s)</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {error && <p className="text-sm text-uni-red">{error}</p>}
      {success && <p className="text-sm text-green-600">{success}</p>}

      {/* Prompt editor */}
      <div className="flex gap-6 h-[calc(100vh-360px)]">
        <div className="w-72 flex-shrink-0 overflow-y-auto">
          {visibleCategories.map(([category, files]) => (
            <div key={category} className="mb-4">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 px-2">{category}</h4>
              {files.map(file => (
                <button
                  key={file.name}
                  onClick={() => selectPrompt(file.name)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                    selected === file.name ? 'bg-uni-blue text-white' : 'text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  <div className="font-medium">{file.name}</div>
                  <div className={`text-xs ${selected === file.name ? 'text-white/70' : 'text-gray-400'}`}>{formatDate(file.modified)}</div>
                </button>
              ))}
            </div>
          ))}
        </div>

        <div className="flex-1 flex flex-col">
          {selected ? (
            <>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-semibold text-gray-800">{selected}{readOnly && <span className="ml-2 text-xs font-normal text-gray-400">(read-only — using global)</span>}</h3>
                <div className="flex items-center gap-3">
                  {dirty && !readOnly && <span className="text-xs text-gray-400">Unsaved changes</span>}
                  <button
                    onClick={() => selected && (!dirty || confirm('Reload from disk and discard unsaved changes?')) && selectPrompt(selected)}
                    className="border border-gray-300 text-gray-600 rounded-lg px-3 py-1.5 text-sm font-medium hover:bg-gray-50"
                  >
                    Reload from disk
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={saving || !dirty || readOnly}
                    className="bg-uni-blue text-white rounded-lg px-4 py-1.5 text-sm font-medium hover:opacity-90 disabled:opacity-50"
                  >
                    {saving ? 'Saving...' : 'Save'}
                  </button>
                </div>
              </div>
              <textarea
                value={content}
                onChange={e => setContent(e.target.value)}
                readOnly={readOnly}
                className={`flex-1 border border-gray-300 rounded-lg p-4 font-mono text-sm resize-none focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none ${readOnly ? 'bg-gray-100 text-gray-500' : ''}`}
                spellCheck={false}
              />
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-gray-400 text-sm">Select a prompt file to edit</p>
            </div>
          )}
        </div>
      </div>

      {/* Reset modal */}
      {resetModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setResetModal(null)}>
          <div className="bg-white rounded-xl shadow-xl border border-gray-200 p-5 w-[32rem] max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-gray-800 mb-1">
              Reset from {resetModal.source === 'factory' ? 'factory' : 'global'}
            </h3>
            <p className="text-xs text-gray-500 mb-3">
              {isFrontend
                ? (resetModal.source === 'factory'
                    ? "Overwrite this frontend's selected prompts with the bundled factory versions."
                    : "Overwrite this frontend's selected prompts with the current global versions.")
                : 'Overwrite the selected global prompts with the bundled factory versions.'}
              {' '}Select which prompts. Leave all unchecked to apply to every prompt.
            </p>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2 border-b border-gray-100 pb-2">
              <input
                type="checkbox"
                checked={resetSelection.size === allVisibleNames.length && allVisibleNames.length > 0}
                onChange={e => setResetSelection(e.target.checked ? new Set(allVisibleNames) : new Set())}
              />
              All prompts
            </label>
            <div className="overflow-y-auto flex-1 space-y-1 mb-4">
              {allVisibleNames.map(name => (
                <label key={name} className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={resetSelection.has(name)}
                    onChange={e => {
                      const next = new Set(resetSelection)
                      if (e.target.checked) next.add(name); else next.delete(name)
                      setResetSelection(next)
                    }}
                  />
                  {name}
                </label>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setResetModal(null)} className="border border-gray-300 text-gray-600 rounded-lg px-3 py-1.5 text-sm hover:bg-gray-50">Cancel</button>
              <button onClick={confirmReset} className="bg-uni-red text-white rounded-lg px-4 py-1.5 text-sm font-medium hover:opacity-90">
                Reset {resetSelection.size > 0 ? `${resetSelection.size} prompt(s)` : 'all'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
