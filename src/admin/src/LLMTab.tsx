import { useState, useEffect, useRef } from 'react'
import { getLLMHealth, getLLMSettings, updateLLMSettings, resetLLMSettings, listFrontends, getFrontendLLMSettings, updateFrontendLLMSettings, deleteFrontendLLMSettings, type LLMHealth, type LLMSettings, type Frontend } from './api'

export default function LLMTab() {
  const [health, setHealth] = useState<LLMHealth | null>(null)
  const [settings, setSettings] = useState<LLMSettings | null>(null)
  const [savedSettings, setSavedSettings] = useState<LLMSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const dirty = useRef(false)

  const refreshHealth = async () => {
    try {
      const h = await getLLMHealth()
      setHealth(h)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load health')
    }
  }

  const loadAll = async () => {
    try {
      const [h, s] = await Promise.all([getLLMHealth(), getLLMSettings()])
      setHealth(h)
      setSettings(s)
      setSavedSettings(s)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    }
  }

  useEffect(() => {
    loadAll()
    // Only refresh health status periodically, not settings (avoids overwriting edits)
    const interval = setInterval(refreshHealth, 15000)
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
      setSavedSettings(updated)
      dirty.current = false
      setSuccess('Settings saved')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    setError('')
    setSuccess('')
    try {
      const defaults = await resetLLMSettings()
      setSettings(defaults)
      setSavedSettings(defaults)
      dirty.current = false
      setSuccess('Settings reset to defaults')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed')
    }
  }

  const handleDiscard = () => {
    if (savedSettings) {
      setSettings({ ...savedSettings })
      dirty.current = false
    }
  }

  const updateField = <K extends keyof LLMSettings>(key: K, value: LLMSettings[K]) => {
    if (!settings) return
    dirty.current = true
    setSettings({ ...settings, [key]: value })
  }

  // Per-frontend LLM overrides
  const [frontends, setFrontends] = useState<Frontend[]>([])
  const [feOverrides, setFeOverrides] = useState<Record<string, Partial<LLMSettings>>>({})
  const [feOpen, setFeOpen] = useState<string | null>(null)
  const [feSaving, setFeSaving] = useState(false)
  const [feSuccess, setFeSuccess] = useState('')

  useEffect(() => {
    listFrontends().then(({ frontends: list }) => setFrontends(list)).catch(() => {})
  }, [])

  const toggleFeOverride = async (fid: string) => {
    if (feOpen === fid) {
      setFeOpen(null)
      return
    }
    try {
      const { override } = await getFrontendLLMSettings(fid)
      setFeOverrides(prev => ({ ...prev, [fid]: override }))
      setFeOpen(fid)
    } catch {
      // ignore
    }
  }

  const updateFeField = <K extends keyof LLMSettings>(fid: string, key: K, value: LLMSettings[K]) => {
    setFeOverrides(prev => ({
      ...prev,
      [fid]: { ...prev[fid], [key]: value },
    }))
  }

  const clearFeField = (fid: string, key: keyof LLMSettings) => {
    setFeOverrides(prev => {
      const copy = { ...prev[fid] }
      delete copy[key]
      return { ...prev, [fid]: copy }
    })
  }

  const handleFeSave = async (fid: string) => {
    setFeSaving(true)
    try {
      const override = feOverrides[fid] || {}
      await updateFrontendLLMSettings(fid, override)
      setFeSuccess('Saved')
      setTimeout(() => setFeSuccess(''), 3000)
    } catch {
      // ignore
    } finally {
      setFeSaving(false)
    }
  }

  const handleFeReset = async (fid: string) => {
    try {
      await deleteFrontendLLMSettings(fid)
      setFeOverrides(prev => ({ ...prev, [fid]: {} }))
      setFeSuccess('Reset to global')
      setTimeout(() => setFeSuccess(''), 3000)
    } catch {
      // ignore
    }
  }

  const statusDot = (status: string) =>
    status === 'online' ? 'bg-green-500' : 'bg-red-500'

  // Sprint 17: per-slot health badge from circuit breaker
  const slotBadge = (slotPrefix: 'inference' | 'reporter' | 'summariser') => {
    if (!health?.slot_health || !settings) return null
    const provider = settings[`${slotPrefix}_provider`]
    const model = settings[`${slotPrefix}_model`]
    const key = `${provider}:${model}`
    const status = health.slot_health[key]
    if (!status) return null // online (no entry = healthy)
    if (status === 'down') {
      return <span className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-red-600 bg-red-50 px-2 py-0.5 rounded-full">Down</span>
    }
    if (status === 'degraded') {
      return <span className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">Degraded</span>
    }
    return null
  }

  const allModels = (provider: string): string[] => {
    if (!health) return []
    if (provider === 'lm_studio') return health.lm_studio.models
    if (provider === 'ollama') return health.ollama.models
    return []
  }

  const hint = (text: string) => (
    <p className="text-xs text-gray-400 mt-1">{text}</p>
  )

  const modelSelector = (
    providerKey: 'inference_provider' | 'reporter_provider' | 'summariser_provider',
    modelKey: 'inference_model' | 'reporter_model' | 'summariser_model',
  ) => {
    if (!settings) return null
    const provider = settings[providerKey]
    const models = allModels(provider)
    const currentModel = settings[modelKey]

    // If current model isn't in the provider's list, auto-correct to first available
    if (models.length > 0 && !models.includes(currentModel)) {
      // Schedule update for next render to avoid updating during render
      setTimeout(() => updateField(modelKey, models[0]), 0)
    }

    return models.length > 0 ? (
      <select
        value={models.includes(currentModel) ? currentModel : models[0]}
        onChange={e => updateField(modelKey, e.target.value)}
        className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
      >
        {models.map(m => (
          <option key={m} value={m}>{m}</option>
        ))}
      </select>
    ) : (
      <input
        type="text"
        value={currentModel}
        onChange={e => updateField(modelKey, e.target.value)}
        placeholder="e.g. qwen3-235b-a22b"
        className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
      />
    )
  }

  return (
    <div className="space-y-6">
      {/* Provider Status */}
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800">LLM Providers</h3>
          <button
            onClick={refreshHealth}
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

      {settings && (
        <>
          {/* Inference Panel */}
          <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-1">Inference{slotBadge('inference')}</h3>
            <p className="text-xs text-gray-400 mb-4">Main LLM that responds to users in chat conversations</p>

            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
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
                <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                {modelSelector('inference_provider', 'inference_model')}
                {settings.multimodal_enabled && hint('Image analysis is ON below — make sure this model supports vision (e.g. Gemma 3/4, Qwen2.5-VL, llava).')}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Temperature ({settings.inference_temperature})
                </label>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={settings.inference_temperature}
                  onChange={e => updateField('inference_temperature', parseFloat(e.target.value))}
                  className="w-full"
                />
                {hint('0 = deterministic, 0.5-0.7 = balanced, >1 = creative. Recommended: 0.7')}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Max Tokens</label>
                <input
                  type="number"
                  value={settings.inference_max_tokens}
                  onChange={e => updateField('inference_max_tokens', parseInt(e.target.value) || 2048)}
                  className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                />
                {hint('Max response length. 1 page ≈ 400 tokens. 2048 ≈ 5 pages.')}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Context Window</label>
                <input
                  type="number"
                  value={settings.inference_num_ctx}
                  onChange={e => updateField('inference_num_ctx', parseInt(e.target.value) || 32768)}
                  className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                />
                {hint(settings.inference_provider === 'ollama'
                  ? 'Overrides Ollama default. Verify your model supports this context length.'
                  : 'Set this to match the context length configured in LM Studio for the loaded model.'
                )}
              </div>
            </div>

            <div className="border-t border-gray-200 pt-4 mt-4">
              <label className="flex items-start gap-3 cursor-pointer">
                <div
                  className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 mt-0.5 ${settings.multimodal_enabled ? 'bg-uni-blue' : 'bg-gray-300'}`}
                  onClick={() => updateField('multimodal_enabled', !settings.multimodal_enabled)}
                >
                  <div
                    className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${settings.multimodal_enabled ? 'translate-x-5' : 'translate-x-0.5'}`}
                  />
                </div>
                <div>
                  <span className="text-sm font-medium text-gray-700">Analyse uploaded images with the inference model</span>
                  <p className="text-xs text-gray-400">
                    Only enable this if the selected inference model supports vision (e.g. Gemma 3/4, Qwen2.5-VL, llava).
                    When on, every uploaded JPG/PNG is described by the inference model at upload time and the description is added to the case evidence.
                    When off (default), images are stored without analysis. Image uploads are slower than text uploads.
                  </p>
                </div>
              </label>
            </div>
          </div>

          {/* Reporter Panel */}
          <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-1">Reporter{slotBadge('reporter')}</h3>
            <p className="text-xs text-gray-400 mb-4">
              Dedicated LLM for generating structured internal documents (case file + UNI summary).
              Use a model specialised for long, factual, well-structured output (e.g. Qwen), while inference keeps a conversational model (e.g. Gemma).
            </p>

            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
                <select
                  value={settings.reporter_provider}
                  onChange={e => updateField('reporter_provider', e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                >
                  <option value="lm_studio">LM Studio</option>
                  <option value="ollama">Ollama</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                {modelSelector('reporter_provider', 'reporter_model')}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Temperature ({settings.reporter_temperature})
                </label>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={settings.reporter_temperature}
                  onChange={e => updateField('reporter_temperature', parseFloat(e.target.value))}
                  className="w-full"
                />
                {hint('Lower = more factual, better for structured reports. Recommended: 0.2-0.4')}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Max Tokens</label>
                <input
                  type="number"
                  value={settings.reporter_max_tokens}
                  onChange={e => updateField('reporter_max_tokens', parseInt(e.target.value) || 4096)}
                  className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                />
                {hint('Reports can be long. Recommended: 4096+')}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Context Window</label>
                <input
                  type="number"
                  value={settings.reporter_num_ctx}
                  onChange={e => updateField('reporter_num_ctx', parseInt(e.target.value) || 32768)}
                  className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                />
                {hint(settings.reporter_provider === 'ollama'
                  ? 'Overrides Ollama default. Verify your model supports this context length.'
                  : 'Set this to match the context length configured in LM Studio for the loaded model.'
                )}
              </div>
            </div>

            <div className="border-t border-gray-200 pt-4">
              <label className="flex items-center gap-3 cursor-pointer">
                <div
                  className={`relative w-10 h-5 rounded-full transition-colors ${settings.use_reporter_for_user_summary ? 'bg-uni-blue' : 'bg-gray-300'}`}
                  onClick={() => updateField('use_reporter_for_user_summary', !settings.use_reporter_for_user_summary)}
                >
                  <div
                    className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${settings.use_reporter_for_user_summary ? 'translate-x-5' : 'translate-x-0.5'}`}
                  />
                </div>
                <div>
                  <span className="text-sm font-medium text-gray-700">Use reporter for user-facing summary</span>
                  <p className="text-xs text-gray-400">
                    When off (default), the user sees a summary generated by the inference model — faster and more conversational.
                    When on, the reporter model writes the user summary too — more structured but slower.
                    Internal documents always use the reporter model regardless of this toggle.
                  </p>
                </div>
              </label>
            </div>
          </div>

          {/* Context Compression Panel */}
          <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-lg font-semibold text-gray-800">Context Compression{slotBadge('summariser')}</h3>
              <label className="flex items-center gap-2 cursor-pointer">
                <span className="text-xs text-gray-500">
                  {settings.summariser_enabled ? 'Enabled' : 'Disabled'}
                </span>
                <div
                  className={`relative w-10 h-5 rounded-full transition-colors ${settings.summariser_enabled ? 'bg-uni-blue' : 'bg-gray-300'}`}
                  onClick={() => updateField('summariser_enabled', !settings.summariser_enabled)}
                >
                  <div
                    className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${settings.summariser_enabled ? 'translate-x-5' : 'translate-x-0.5'}`}
                  />
                </div>
              </label>
            </div>
            <p className="text-xs text-gray-400 mb-4">
              Incrementally compresses conversation history to prevent context overflow in the inference model.
              Uses a separate, smaller LLM to summarize older messages while preserving all names, dates, and case facts.
              {!settings.summariser_enabled && ' When disabled, long conversations may be truncated by the inference model.'}
            </p>

            {settings.summariser_enabled && (
              <>
                <div className="grid grid-cols-2 gap-4 mb-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
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
                    <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                    {modelSelector('summariser_provider', 'summariser_model')}
                    {hint('Recommended: qwen2.5:3b, phi-3.5-mini, gemma3:4b — small and fast.')}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Temperature ({settings.summariser_temperature})
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.1"
                      value={settings.summariser_temperature}
                      onChange={e => updateField('summariser_temperature', parseFloat(e.target.value))}
                      className="w-full"
                    />
                    {hint('Lower = more factual. Recommended: 0.2-0.3')}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Context Window</label>
                    <input
                      type="number"
                      value={settings.summariser_num_ctx}
                      onChange={e => updateField('summariser_num_ctx', parseInt(e.target.value) || 8192)}
                      className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                    />
                    {hint(settings.summariser_provider === 'ollama'
                      ? 'Overrides Ollama default. Verify your model supports this context length.'
                      : 'Set this to match the context length configured in LM Studio for the compression model.'
                    )}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      First Compression ({(settings.compression_first_threshold ?? 20000).toLocaleString()} tokens)
                    </label>
                    <input
                      type="range"
                      min="10000"
                      max="50000"
                      step="5000"
                      value={settings.compression_first_threshold ?? 20000}
                      onChange={e => updateField('compression_first_threshold', parseInt(e.target.value))}
                      className="w-full"
                    />
                    {hint('First compression triggers when context reaches this token count.')}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Compression Step ({(settings.compression_step_size ?? 15000).toLocaleString()} tokens)
                    </label>
                    <input
                      type="range"
                      min="10000"
                      max="50000"
                      step="5000"
                      value={settings.compression_step_size ?? 15000}
                      onChange={e => updateField('compression_step_size', parseInt(e.target.value))}
                      className="w-full"
                    />
                    {hint(`After first compression, compress again every ${((settings.compression_step_size ?? 15000) / 1000).toFixed(0)}k tokens. Next compressions at: ${[1,2,3].map(i => ((settings.compression_first_threshold ?? 20000) + i * (settings.compression_step_size ?? 15000)) / 1000).map(v => v + 'k').join(', ')}...`)}
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={saving}
              className="bg-uni-blue text-white rounded-lg px-5 py-2 text-sm font-medium transition-colors hover:opacity-90 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save Settings'}
            </button>
            <button
              onClick={handleDiscard}
              className="border border-gray-300 text-gray-600 rounded-lg px-4 py-2 text-sm font-medium transition-colors hover:bg-gray-50"
            >
              Discard Changes
            </button>
            <button
              onClick={handleReset}
              className="text-xs text-gray-400 hover:text-uni-red transition-colors px-2 py-2"
            >
              Reset to Defaults
            </button>
            {success && <span className="text-sm text-green-600">{success}</span>}
            {error && <span className="text-sm text-uni-red">{error}</span>}
          </div>

          {/* Per-Frontend LLM Overrides */}
          {frontends.length > 0 && (
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
              <h3 className="text-lg font-semibold text-gray-800 mb-1">Per-Frontend LLM</h3>
              <p className="text-xs text-gray-400 mb-4">
                Override inference and/or reporter slots for specific frontends. Frontends without overrides use the global settings above.
              </p>
              <div className="space-y-3">
                {frontends.map(f => {
                  const override = feOverrides[f.id] || {}
                  const hasOverride = Object.keys(override).length > 0
                  return (
                    <div key={f.id} className="border border-gray-200 rounded-lg px-4 py-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className={`w-2.5 h-2.5 rounded-full ${statusDot(f.status)}`} />
                          <div>
                            <span className="text-sm font-medium text-gray-800">{f.name}</span>
                            <span className="text-xs text-gray-400 ml-2">{f.url}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {feOpen !== f.id && hasOverride && (
                            <span className="text-xs text-uni-blue font-medium">Custom LLM</span>
                          )}
                          {feOpen !== f.id && !hasOverride && (
                            <span className="text-xs text-gray-400">Using global</span>
                          )}
                          <button
                            onClick={() => toggleFeOverride(f.id)}
                            className="text-xs px-3 py-1 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 font-medium transition-colors"
                          >
                            {feOpen === f.id ? 'Close' : 'Configure'}
                          </button>
                        </div>
                      </div>

                      {feOpen === f.id && settings && (
                        <div className="mt-4 pt-4 border-t border-gray-200 space-y-4">
                          <div>
                            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Inference</div>
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="block text-xs font-medium text-gray-600 mb-1">
                                Provider
                                {override.inference_provider
                                  ? <button onClick={() => clearFeField(f.id, 'inference_provider')} className="ml-2 text-xs text-gray-400 hover:text-uni-red">reset</button>
                                  : <span className="ml-2 text-xs text-gray-400">(global: {settings.inference_provider})</span>
                                }
                              </label>
                              <select
                                value={override.inference_provider ?? settings.inference_provider}
                                onChange={e => updateFeField(f.id, 'inference_provider', e.target.value)}
                                className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                              >
                                <option value="lm_studio">LM Studio</option>
                                <option value="ollama">Ollama</option>
                              </select>
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-gray-600 mb-1">
                                Model
                                {override.inference_model
                                  ? <button onClick={() => clearFeField(f.id, 'inference_model')} className="ml-2 text-xs text-gray-400 hover:text-uni-red">reset</button>
                                  : <span className="ml-2 text-xs text-gray-400">(global: {settings.inference_model})</span>
                                }
                              </label>
                              {(() => {
                                const provider = override.inference_provider ?? settings.inference_provider
                                const models = allModels(provider)
                                const current = override.inference_model ?? settings.inference_model
                                return models.length > 0 ? (
                                  <select
                                    value={models.includes(current) ? current : models[0]}
                                    onChange={e => updateFeField(f.id, 'inference_model', e.target.value)}
                                    className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                                  >
                                    {models.map(m => (
                                      <option key={m} value={m}>{m}</option>
                                    ))}
                                  </select>
                                ) : (
                                  <input
                                    type="text"
                                    value={current}
                                    onChange={e => updateFeField(f.id, 'inference_model', e.target.value)}
                                    placeholder="e.g. qwen3-235b-a22b"
                                    className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                                  />
                                )
                              })()}
                            </div>
                          </div>
                          <div className="grid grid-cols-3 gap-3">
                            <div>
                              <label className="block text-xs font-medium text-gray-600 mb-1">
                                Temperature ({(override.inference_temperature ?? settings.inference_temperature)})
                                {override.inference_temperature != null
                                  ? <button onClick={() => clearFeField(f.id, 'inference_temperature')} className="ml-1 text-xs text-gray-400 hover:text-uni-red">reset</button>
                                  : null
                                }
                              </label>
                              <input
                                type="range" min="0" max="2" step="0.1"
                                value={override.inference_temperature ?? settings.inference_temperature}
                                onChange={e => updateFeField(f.id, 'inference_temperature', parseFloat(e.target.value))}
                                className="w-full"
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-gray-600 mb-1">
                                Max Tokens
                                {override.inference_max_tokens != null
                                  ? <button onClick={() => clearFeField(f.id, 'inference_max_tokens')} className="ml-1 text-xs text-gray-400 hover:text-uni-red">reset</button>
                                  : null
                                }
                              </label>
                              <input
                                type="number"
                                value={override.inference_max_tokens ?? settings.inference_max_tokens}
                                onChange={e => updateFeField(f.id, 'inference_max_tokens', parseInt(e.target.value) || 2048)}
                                className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-gray-600 mb-1">
                                Context Window
                                {override.inference_num_ctx != null
                                  ? <button onClick={() => clearFeField(f.id, 'inference_num_ctx')} className="ml-1 text-xs text-gray-400 hover:text-uni-red">reset</button>
                                  : null
                                }
                              </label>
                              <input
                                type="number"
                                value={override.inference_num_ctx ?? settings.inference_num_ctx}
                                onChange={e => updateFeField(f.id, 'inference_num_ctx', parseInt(e.target.value) || 32768)}
                                className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                              />
                            </div>
                          </div>
                          </div>

                          <div className="pt-3 border-t border-gray-100">
                            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Reporter</div>
                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">
                                  Provider
                                  {override.reporter_provider
                                    ? <button onClick={() => clearFeField(f.id, 'reporter_provider')} className="ml-2 text-xs text-gray-400 hover:text-uni-red">reset</button>
                                    : <span className="ml-2 text-xs text-gray-400">(global: {settings.reporter_provider})</span>
                                  }
                                </label>
                                <select
                                  value={override.reporter_provider ?? settings.reporter_provider}
                                  onChange={e => updateFeField(f.id, 'reporter_provider', e.target.value)}
                                  className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                                >
                                  <option value="lm_studio">LM Studio</option>
                                  <option value="ollama">Ollama</option>
                                </select>
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">
                                  Model
                                  {override.reporter_model
                                    ? <button onClick={() => clearFeField(f.id, 'reporter_model')} className="ml-2 text-xs text-gray-400 hover:text-uni-red">reset</button>
                                    : <span className="ml-2 text-xs text-gray-400">(global: {settings.reporter_model})</span>
                                  }
                                </label>
                                {(() => {
                                  const provider = override.reporter_provider ?? settings.reporter_provider
                                  const models = allModels(provider)
                                  const current = override.reporter_model ?? settings.reporter_model
                                  return models.length > 0 ? (
                                    <select
                                      value={models.includes(current) ? current : models[0]}
                                      onChange={e => updateFeField(f.id, 'reporter_model', e.target.value)}
                                      className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                                    >
                                      {models.map(m => (
                                        <option key={m} value={m}>{m}</option>
                                      ))}
                                    </select>
                                  ) : (
                                    <input
                                      type="text"
                                      value={current}
                                      onChange={e => updateFeField(f.id, 'reporter_model', e.target.value)}
                                      placeholder="e.g. qwen3-235b-a22b"
                                      className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                                    />
                                  )
                                })()}
                              </div>
                            </div>
                            <div className="grid grid-cols-3 gap-3 mt-3">
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">
                                  Temperature ({(override.reporter_temperature ?? settings.reporter_temperature)})
                                  {override.reporter_temperature != null
                                    ? <button onClick={() => clearFeField(f.id, 'reporter_temperature')} className="ml-1 text-xs text-gray-400 hover:text-uni-red">reset</button>
                                    : null
                                  }
                                </label>
                                <input
                                  type="range" min="0" max="2" step="0.1"
                                  value={override.reporter_temperature ?? settings.reporter_temperature}
                                  onChange={e => updateFeField(f.id, 'reporter_temperature', parseFloat(e.target.value))}
                                  className="w-full"
                                />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">
                                  Max Tokens
                                  {override.reporter_max_tokens != null
                                    ? <button onClick={() => clearFeField(f.id, 'reporter_max_tokens')} className="ml-1 text-xs text-gray-400 hover:text-uni-red">reset</button>
                                    : null
                                  }
                                </label>
                                <input
                                  type="number"
                                  value={override.reporter_max_tokens ?? settings.reporter_max_tokens}
                                  onChange={e => updateFeField(f.id, 'reporter_max_tokens', parseInt(e.target.value) || 4096)}
                                  className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                                />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">
                                  Context Window
                                  {override.reporter_num_ctx != null
                                    ? <button onClick={() => clearFeField(f.id, 'reporter_num_ctx')} className="ml-1 text-xs text-gray-400 hover:text-uni-red">reset</button>
                                    : null
                                  }
                                </label>
                                <input
                                  type="number"
                                  value={override.reporter_num_ctx ?? settings.reporter_num_ctx}
                                  onChange={e => updateFeField(f.id, 'reporter_num_ctx', parseInt(e.target.value) || 32768)}
                                  className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
                                />
                              </div>
                            </div>
                          </div>

                          <div className="flex items-center gap-3">
                            <button
                              onClick={() => handleFeSave(f.id)}
                              disabled={feSaving}
                              className="bg-uni-blue text-white rounded-lg px-4 py-1.5 text-sm font-medium hover:opacity-90 disabled:opacity-50"
                            >
                              {feSaving ? 'Saving...' : 'Save Override'}
                            </button>
                            <button
                              onClick={() => handleFeReset(f.id)}
                              className="text-xs text-gray-400 hover:text-uni-red transition-colors px-2"
                            >
                              Remove Override (use global)
                            </button>
                            {feSuccess && feOpen === f.id && <span className="text-xs text-green-600">{feSuccess}</span>}
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
