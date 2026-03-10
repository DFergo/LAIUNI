import { useState, useEffect } from 'react'
import { getLLMHealth, getLLMSettings, updateLLMSettings, type LLMHealth, type LLMSettings } from './api'

export default function LLMTab() {
  const [health, setHealth] = useState<LLMHealth | null>(null)
  const [settings, setSettings] = useState<LLMSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const refresh = async () => {
    try {
      const [h, s] = await Promise.all([getLLMHealth(), getLLMSettings()])
      setHealth(h)
      setSettings(s)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    }
  }

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 15000)
    return () => clearInterval(interval)
  }, [])

  const handleSave = async () => {
    if (!settings) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const updated = await updateLLMSettings(settings)
      setSettings(updated)
      setSuccess('Settings saved')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const updateField = <K extends keyof LLMSettings>(key: K, value: LLMSettings[K]) => {
    if (!settings) return
    setSettings({ ...settings, [key]: value })
  }

  const statusDot = (status: string) => {
    if (status === 'online') return 'bg-green-500'
    return 'bg-red-500'
  }

  const allModels = (provider: string): string[] => {
    if (!health) return []
    if (provider === 'lm_studio') return health.lm_studio.models
    if (provider === 'ollama') return health.ollama.models
    return []
  }

  return (
    <div className="space-y-6">
      {/* Provider Status */}
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800">LLM Providers</h3>
          <button
            onClick={refresh}
            className="text-xs px-3 py-1 rounded-lg border border-gray-300 text-gray-500 hover:bg-gray-50 font-medium transition-colors"
          >
            Refresh
          </button>
        </div>
        {health ? (
          <div className="grid grid-cols-2 gap-4">
            <div className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-2.5 h-2.5 rounded-full ${statusDot(health.lm_studio.status)}`} />
                <span className="font-medium text-gray-800">LM Studio</span>
              </div>
              <div className="text-xs text-gray-400">
                {health.lm_studio.status === 'online'
                  ? `${health.lm_studio.models.length} model(s) loaded`
                  : health.lm_studio.error || 'Offline'}
              </div>
            </div>
            <div className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-2.5 h-2.5 rounded-full ${statusDot(health.ollama.status)}`} />
                <span className="font-medium text-gray-800">Ollama</span>
              </div>
              <div className="text-xs text-gray-400">
                {health.ollama.status === 'online'
                  ? `${health.ollama.models.length} model(s) available`
                  : health.ollama.error || 'Offline'}
              </div>
            </div>
          </div>
        ) : (
          <p className="text-gray-400 text-sm">Loading...</p>
        )}
      </div>

      {/* Settings */}
      {settings && (
        <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">Inference Settings</h3>
          <div className="grid grid-cols-2 gap-4">
            {/* Inference slot */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Inference Provider</label>
              <select
                value={settings.inference_provider}
                onChange={e => updateField('inference_provider', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
              >
                <option value="lm_studio">LM Studio</option>
                <option value="ollama">Ollama</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Inference Model</label>
              {allModels(settings.inference_provider).length > 0 ? (
                <select
                  value={settings.inference_model}
                  onChange={e => updateField('inference_model', e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                >
                  {allModels(settings.inference_provider).map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={settings.inference_model}
                  onChange={e => updateField('inference_model', e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                />
              )}
            </div>

            {/* Summariser slot */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Summariser Provider</label>
              <select
                value={settings.summariser_provider}
                onChange={e => updateField('summariser_provider', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
              >
                <option value="lm_studio">LM Studio</option>
                <option value="ollama">Ollama</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Summariser Model</label>
              {allModels(settings.summariser_provider).length > 0 ? (
                <select
                  value={settings.summariser_model}
                  onChange={e => updateField('summariser_model', e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                >
                  {allModels(settings.summariser_provider).map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={settings.summariser_model}
                  onChange={e => updateField('summariser_model', e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                />
              )}
            </div>
          </div>

          <h3 className="text-lg font-semibold text-gray-800 mt-6 mb-4">Parameters</h3>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Temperature ({settings.temperature})
              </label>
              <input
                type="range"
                min="0"
                max="2"
                step="0.1"
                value={settings.temperature}
                onChange={e => updateField('temperature', parseFloat(e.target.value))}
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Max Tokens</label>
              <input
                type="number"
                value={settings.max_tokens}
                onChange={e => updateField('max_tokens', parseInt(e.target.value) || 2048)}
                className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Context Window (num_ctx)</label>
              <input
                type="number"
                value={settings.num_ctx}
                onChange={e => updateField('num_ctx', parseInt(e.target.value) || 8192)}
                className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
              />
            </div>
          </div>

          <div className="mt-6 flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={saving}
              className="bg-uni-blue text-white rounded-lg px-5 py-2 text-sm font-medium transition-colors hover:opacity-90 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
            {success && <span className="text-sm text-green-600">{success}</span>}
            {error && <span className="text-sm text-uni-red">{error}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
