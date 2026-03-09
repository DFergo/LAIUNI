import { useState, useEffect } from 'react'
import { t } from './i18n'
import type { Phase, LangCode, DeploymentConfig, SurveyData } from './types'
import LanguageSelector from './components/LanguageSelector'
import DisclaimerPage from './components/DisclaimerPage'
import SessionPage from './components/SessionPage'
import AuthPage from './components/AuthPage'
import SurveyPage from './components/SurveyPage'
import ChatShell from './components/ChatShell'

function App() {
  const [phase, setPhase] = useState<Phase>('loading')
  const [lang, setLang] = useState<LangCode>('en')
  const [config, setConfig] = useState<DeploymentConfig | null>(null)
  const [sessionToken, setSessionToken] = useState('')
  const [_survey, setSurvey] = useState<SurveyData | null>(null)

  useEffect(() => {
    fetchConfig()
  }, [])

  async function fetchConfig() {
    try {
      const res = await fetch('/internal/config')
      if (res.ok) {
        const data: DeploymentConfig = await res.json()
        setConfig(data)
      }
    } catch {
      // Config fetch failed — use defaults
    }
    setPhase('language')
  }

  const handleLanguage = (selected: LangCode) => {
    setLang(selected)
    if (config?.disclaimer_enabled === false) {
      setPhase('session')
    } else {
      setPhase('disclaimer')
    }
  }

  const handleDisclaimer = () => {
    setPhase('session')
  }

  const handleNewSession = (token: string) => {
    setSessionToken(token)
    if (config?.auth_required) {
      setPhase('auth')
    } else {
      setPhase('survey')
    }
  }

  const handleRecover = async (token: string) => {
    // Sprint 8 will implement actual recovery via GET /internal/session/{token}/recover
    // For now, treat as new session with provided token
    setSessionToken(token)
    if (config?.auth_required) {
      setPhase('auth')
    } else {
      setPhase('survey')
    }
  }

  const handleAuth = () => {
    setPhase('survey')
  }

  const handleSurvey = (data: SurveyData) => {
    setSurvey(data)
    setPhase('chat')
  }

  const showFooter = phase !== 'chat' && phase !== 'loading'

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-uni-blue text-white px-6 py-4 shadow-md flex items-center justify-between">
        <h1 className="text-xl font-semibold">HRDD Helper</h1>
        <span className="text-sm opacity-75">UNI Global Union</span>
      </header>

      <main className="flex-1">
        {phase === 'loading' && (
          <div className="flex items-center justify-center mt-20">
            <p className="text-gray-400">Loading...</p>
          </div>
        )}
        {phase === 'language' && <LanguageSelector onSelect={handleLanguage} />}
        {phase === 'disclaimer' && <DisclaimerPage lang={lang} onAccept={handleDisclaimer} />}
        {phase === 'session' && <SessionPage lang={lang} onNewSession={handleNewSession} onRecover={handleRecover} />}
        {phase === 'auth' && <AuthPage lang={lang} onVerified={handleAuth} />}
        {phase === 'survey' && config && <SurveyPage lang={lang} config={config} onSubmit={handleSurvey} />}
        {phase === 'chat' && <ChatShell lang={lang} sessionToken={sessionToken} />}
      </main>

      {showFooter && (
        <footer className="text-center text-xs text-gray-400 py-3">
          {t('footer_disclaimer', lang)}
        </footer>
      )}
    </div>
  )
}

export default App
