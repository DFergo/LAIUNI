import { useState } from 'react'
import { t } from '../i18n'
import type { LangCode, Role, ConsultationMode, SurveyData, DeploymentConfig } from '../types'

interface Props {
  lang: LangCode
  config: DeploymentConfig
  onSubmit: (data: SurveyData) => void
}

const ROLES: Role[] = ['worker', 'representative', 'organizer', 'officer']
const MODES: ConsultationMode[] = ['documentation', 'advisory', 'training']

export default function SurveyPage({ lang, config, onSubmit }: Props) {
  const [role, setRole] = useState<Role>('worker')
  const [mode, setMode] = useState<ConsultationMode>('documentation')
  const [name, setName] = useState('')
  const [position, setPosition] = useState('')
  const [union, setUnion] = useState('')
  const [email, setEmail] = useState('')
  const [company, setCompany] = useState('')
  const [countryRegion, setCountryRegion] = useState('')
  const [description, setDescription] = useState('')

  // Field visibility and required logic
  const isOrganizer = config.frontend_type === 'organizer'
  const showMode = role === 'organizer' || role === 'officer'
  // Name, Position, Union, Email: always visible. Required on organizer frontend, optional on worker.
  const identityRequired = isOrganizer
  // Company, Country/Region: required except in training mode
  const companyCountryRequired = !showMode || mode !== 'training'

  // Worker frontend: only worker/representative. Organizer frontend: all 4 roles.
  const availableRoles = config.frontend_type === 'worker'
    ? ROLES.filter(r => r === 'worker' || r === 'representative')
    : ROLES

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const data: SurveyData = {
      role,
      description,
      ...(showMode && { type: mode }),
      ...(name && { name }),
      ...(position && { position }),
      ...(union && { union }),
      ...(email && { email }),
      ...(company && { company }),
      ...(countryRegion && { countryRegion }),
    }
    onSubmit(data)
  }

  return (
    <div className="max-w-4xl mx-auto mt-8 p-6">
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-6">{t('survey_title', lang)}</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Role select — always shown */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('survey_role', lang)}</label>
            <div className="grid grid-cols-2 gap-2">
              {availableRoles.map(r => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRole(r)}
                  className={`px-3 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                    role === r
                      ? 'bg-uni-blue text-white border-uni-blue'
                      : 'border-gray-300 text-gray-700 hover:border-uni-blue hover:bg-blue-50'
                  }`}
                >
                  {t(`role_${r}` as Parameters<typeof t>[0], lang)}
                </button>
              ))}
            </div>
          </div>

          {/* Mode select — organizer/officer only */}
          {showMode && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('survey_mode', lang)}</label>
              <div className="grid grid-cols-3 gap-2">
                {MODES.map(m => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMode(m)}
                    className={`px-3 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                      mode === m
                        ? 'bg-uni-blue text-white border-uni-blue'
                        : 'border-gray-300 text-gray-700 hover:border-uni-blue hover:bg-blue-50'
                    }`}
                  >
                    {t(`mode_${m}` as Parameters<typeof t>[0], lang)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Name — always visible, required on organizer frontend */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('survey_name', lang)}{identityRequired && <span className="text-uni-red ml-0.5">*</span>}
            </label>
            <input type="text" value={name} onChange={e => setName(e.target.value)}
              required={identityRequired}
              className="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
          </div>

          {/* Position — always visible, required on organizer frontend */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('survey_position', lang)}{identityRequired && <span className="text-uni-red ml-0.5">*</span>}
            </label>
            <input type="text" value={position} onChange={e => setPosition(e.target.value)}
              required={identityRequired}
              className="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
          </div>

          {/* Union — always visible, required on organizer frontend */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('survey_union', lang)}{identityRequired && <span className="text-uni-red ml-0.5">*</span>}
            </label>
            <input type="text" value={union} onChange={e => setUnion(e.target.value)}
              required={identityRequired}
              className="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
          </div>

          {/* Email — always visible, required on organizer frontend */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('survey_email', lang)}{identityRequired && <span className="text-uni-red ml-0.5">*</span>}
            </label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              required={identityRequired}
              className="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
          </div>

          {/* Company — always visible, required except training mode */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('survey_company', lang)}{companyCountryRequired && <span className="text-uni-red ml-0.5">*</span>}
            </label>
            <input type="text" value={company} onChange={e => setCompany(e.target.value)}
              required={companyCountryRequired}
              className="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
          </div>

          {/* Country/Region — always visible, required except training mode */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('survey_country', lang)}{companyCountryRequired && <span className="text-uni-red ml-0.5">*</span>}
            </label>
            <input type="text" value={countryRegion} onChange={e => setCountryRegion(e.target.value)}
              required={companyCountryRequired}
              className="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
          </div>

          {/* Situation description — always shown */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('survey_description', lang)}</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={4}
              className="w-full border border-gray-300 rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none resize-none"
              required
            />
          </div>

          <button
            type="submit"
            className="w-full bg-uni-blue text-white rounded-lg px-4 py-2.5 font-medium transition-colors hover:opacity-90"
          >
            {t('survey_submit', lang)}
          </button>
        </form>
      </div>
    </div>
  )
}
