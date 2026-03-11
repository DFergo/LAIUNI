import { useState, useEffect } from 'react'
import { t } from './i18n'
import type { Phase, LangCode, Role, DeploymentConfig, SurveyData, RecoveryData } from './types'
import LanguageSelector from './components/LanguageSelector'
import DisclaimerPage from './components/DisclaimerPage'
import SessionPage from './components/SessionPage'
import RoleSelectPage from './components/RoleSelectPage'
import AuthPage from './components/AuthPage'
import InstructionsPage from './components/InstructionsPage'
import SurveyPage from './components/SurveyPage'
import ChatShell from './components/ChatShell'

function App() {
  const [phase, setPhase] = useState<Phase>('loading')
  const [lang, setLang] = useState<LangCode>('en')
  const [config, setConfig] = useState<DeploymentConfig | null>(null)
  const [sessionToken, setSessionToken] = useState('')
  const [selectedRole, setSelectedRole] = useState<Role | null>(null)
  const [survey, setSurvey] = useState<SurveyData | null>(null)
  const [recoveryData, setRecoveryData] = useState<RecoveryData | null>(null)

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

  // language → disclaimer (or skip) → session
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

  // session → role_select
  const handleNewSession = (token: string) => {
    setSessionToken(token)
    setPhase('role_select')
  }

  const handleRecover = async (token: string): Promise<string | null> => {
    setSessionToken(token)

    // Step 1: Request recovery via sidecar
    try {
      const res = await fetch('/internal/session/recover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      if (!res.ok) return 'Invalid token format'
    } catch {
      return 'Connection error. Please try again.'
    }

    // Step 2: Poll sidecar for recovery result (backend resolves via pull-inverse)
    const maxAttempts = 10
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(r => setTimeout(r, 1000))
      try {
        const res = await fetch(`/internal/session/${token}/recover`)
        if (!res.ok) continue
        const result = await res.json()

        if (result.status === 'pending') continue

        if (result.status === 'found' && result.data) {
          const data = result.data as RecoveryData
          setLang(data.language || lang)
          setSelectedRole(data.role as Role)
          setSurvey(data.survey)
          setRecoveryData(data)
          setPhase('chat')
          return null // success
        }

        if (result.status === 'expired') {
          return 'Session expired. Please start a new session.'
        }

        return 'Session not found.'
      } catch {
        continue
      }
    }

    return 'Recovery timed out. Please try again.'
  }

  // role_select → auth (if required) → instructions
  const handleRoleSelect = (role: Role) => {
    setSelectedRole(role)
    if (config?.auth_required) {
      setPhase('auth')
    } else {
      setPhase('instructions')
    }
  }

  const handleAuth = () => {
    setPhase('instructions')
  }

  // instructions → survey
  const handleInstructions = () => {
    setPhase('survey')
  }

  // survey → chat
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
        {phase === 'role_select' && config && <RoleSelectPage lang={lang} config={config} onSelect={handleRoleSelect} />}
        {phase === 'auth' && <AuthPage lang={lang} onVerified={handleAuth} />}
        {phase === 'instructions' && selectedRole && <InstructionsPage lang={lang} role={selectedRole} onContinue={handleInstructions} />}
        {phase === 'survey' && config && selectedRole && <SurveyPage lang={lang} config={config} role={selectedRole} onSubmit={handleSurvey} />}
        {phase === 'chat' && survey && (
          <ChatShell
            lang={lang}
            sessionToken={sessionToken}
            survey={survey}
            recoveryData={recoveryData}
          />
        )}
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
