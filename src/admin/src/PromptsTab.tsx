import { useState, useEffect } from 'react'
import { listPrompts, readPrompt, savePrompt, type PromptFile } from './api'

export default function PromptsTab() {
  const [categories, setCategories] = useState<Record<string, PromptFile[]>>({})
  const [selected, setSelected] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [originalContent, setOriginalContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadPrompts()
  }, [])

  const loadPrompts = async () => {
    try {
      const data = await listPrompts()
      setCategories(data.categories)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load prompts')
    } finally {
      setLoading(false)
    }
  }

  const selectPrompt = async (name: string) => {
    setError('')
    setSuccess('')
    try {
      const data = await readPrompt(name)
      setSelected(name)
      setContent(data.content)
      setOriginalContent(data.content)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load prompt')
    }
  }

  const handleSave = async () => {
    if (!selected) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      await savePrompt(selected, content)
      setOriginalContent(content)
      setSuccess('Saved')
      setTimeout(() => setSuccess(''), 3000)
      loadPrompts()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const formatDate = (ts: number | null) => {
    if (!ts) return '—'
    return new Date(ts * 1000).toLocaleString()
  }

  const dirty = content !== originalContent

  if (loading) return <p className="text-gray-400 text-sm">Loading...</p>

  return (
    <div className="flex gap-6 h-[calc(100vh-200px)]">
      {/* Left: file list */}
      <div className="w-72 flex-shrink-0 overflow-y-auto">
        {Object.entries(categories).map(([category, files]) => (
          <div key={category} className="mb-4">
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 px-2">
              {category}
            </h4>
            {files.map(file => (
              <button
                key={file.name}
                onClick={() => selectPrompt(file.name)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                  selected === file.name
                    ? 'bg-uni-blue text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                <div className="font-medium">{file.name}</div>
                <div className={`text-xs ${selected === file.name ? 'text-white/70' : 'text-gray-400'}`}>
                  {formatDate(file.modified)}
                </div>
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* Right: editor */}
      <div className="flex-1 flex flex-col">
        {selected ? (
          <>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-semibold text-gray-800">{selected}</h3>
              <div className="flex items-center gap-3">
                {dirty && <span className="text-xs text-gray-400">Unsaved changes</span>}
                {success && <span className="text-sm text-green-600">{success}</span>}
                {error && <span className="text-sm text-uni-red">{error}</span>}
                <button
                  onClick={handleSave}
                  disabled={saving || !dirty}
                  className="bg-uni-blue text-white rounded-lg px-4 py-1.5 text-sm font-medium transition-colors hover:opacity-90 disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
            <textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              className="flex-1 border border-gray-300 rounded-lg p-4 font-mono text-sm resize-none focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
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
  )
}
