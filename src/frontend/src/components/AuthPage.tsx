import { useState } from 'react'
import { t } from '../i18n'
import type { LangCode } from '../types'

interface Props {
  lang: LangCode
  onVerified: () => void
}

export default function AuthPage({ lang, onVerified }: Props) {
  const [email, setEmail] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSendCode = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      // Sprint 9 will implement actual SMTP sending
      // For now, simulate code sent
      await new Promise(r => setTimeout(r, 500))
      setCodeSent(true)
    } catch {
      setError('Failed to send code')
    } finally {
      setLoading(false)
    }
  }

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      // Sprint 9 will implement actual verification
      // For now, accept any 6-digit code
      if (code.length === 6 && /^\d+$/.test(code)) {
        onVerified()
      } else {
        setError('Invalid code format')
      }
    } catch {
      setError('Verification failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto mt-8 p-6">
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-6">{t('auth_title', lang)}</h2>

        {!codeSent ? (
          <form onSubmit={handleSendCode} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('auth_email_label', lang)}</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none transition-colors"
                required
              />
            </div>
            {error && <p className="text-uni-red text-sm">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-uni-blue text-white rounded-lg px-4 py-2.5 font-medium transition-colors hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '...' : t('auth_send_code', lang)}
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerify} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('auth_code_label', lang)}</label>
              <input
                type="text"
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder={t('auth_placeholder', lang)}
                className="w-full border border-gray-300 rounded-lg px-4 py-2.5 text-center text-2xl tracking-[0.5em] font-mono focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none transition-colors"
                maxLength={6}
                required
                autoFocus
              />
            </div>
            {error && <p className="text-uni-red text-sm">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-uni-blue text-white rounded-lg px-4 py-2.5 font-medium transition-colors hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '...' : t('auth_verify', lang)}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
