import { useState, useEffect } from 'react'
import { getSMTPConfig, updateSMTPConfig, testSMTP, type SMTPConfig } from './api'

export default function SMTPTab() {
  const [config, setConfig] = useState<SMTPConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null)

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    try {
      const cfg = await getSMTPConfig()
      setConfig(cfg)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load SMTP config')
    }
  }

  const updateField = <K extends keyof SMTPConfig>(key: K, value: SMTPConfig[K]) => {
    if (!config) return
    setConfig({ ...config, [key]: value })
  }

  const handleSave = async () => {
    if (!config) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const updated = await updateSMTPConfig(config)
      setConfig(updated)
      setSuccess('SMTP settings saved')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    setError('')
    try {
      const result = await testSMTP()
      setTestResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Test failed')
    } finally {
      setTesting(false)
    }
  }

  if (!config) return <p className="text-gray-400 text-sm">Loading...</p>

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-1">SMTP Configuration</h3>
        <p className="text-xs text-gray-400 mb-4">
          Used for email verification (organizer auth), report delivery, and admin notifications.
        </p>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">SMTP Host</label>
            <input
              type="text"
              value={config.host}
              onChange={e => updateField('host', e.target.value)}
              placeholder="smtp.example.com"
              className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Port</label>
            <input
              type="number"
              value={config.port}
              onChange={e => updateField('port', parseInt(e.target.value) || 587)}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
            />
            <p className="text-xs text-gray-400 mt-1">587 for TLS, 465 for SSL, 25 for unencrypted</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
            <input
              type="text"
              value={config.username}
              onChange={e => updateField('username', e.target.value)}
              placeholder="user@example.com"
              className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              type="password"
              value={config.password}
              onChange={e => updateField('password', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">From Address</label>
            <input
              type="email"
              value={config.from_address}
              onChange={e => updateField('from_address', e.target.value)}
              placeholder="hrdd@example.com"
              className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Admin Notification Address</label>
            <input
              type="email"
              value={config.admin_notify_address}
              onChange={e => updateField('admin_notify_address', e.target.value)}
              placeholder="admin@example.com"
              className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none"
            />
            <p className="text-xs text-gray-400 mt-1">Receives alerts for completed/flagged sessions</p>
          </div>
        </div>

        <div className="mb-6">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={config.use_tls}
              onChange={e => updateField('use_tls', e.target.checked)}
              className="rounded border-gray-300 text-uni-blue focus:ring-uni-blue"
            />
            <span className="text-sm text-gray-700">Use TLS encryption</span>
          </label>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-uni-blue text-white rounded-lg px-5 py-2 text-sm font-medium transition-colors hover:opacity-90 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
          <button
            onClick={handleTest}
            disabled={testing || !config.host}
            className="border border-gray-300 text-gray-600 rounded-lg px-4 py-2 text-sm font-medium transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
          {success && <span className="text-sm text-green-600">{success}</span>}
          {error && <span className="text-sm text-uni-red">{error}</span>}
        </div>

        {testResult && (
          <div className={`mt-4 p-3 rounded-lg text-sm ${
            testResult.status === 'success' ? 'bg-green-50 text-green-700' : 'bg-yellow-50 text-yellow-700'
          }`}>
            {testResult.message}
          </div>
        )}
      </div>
    </div>
  )
}
