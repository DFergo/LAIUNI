export type Phase = 'loading' | 'language' | 'disclaimer' | 'session' | 'role_select' | 'auth' | 'instructions' | 'survey' | 'chat'

export type Role = 'worker' | 'representative' | 'organizer' | 'officer'

export type ConsultationMode = 'documentation' | 'interview' | 'advisory' | 'submit' | 'training'

export interface DeploymentConfig {
  role: string
  frontend_type: 'worker' | 'organizer'
  session_resume_window_hours: number
  disclaimer_enabled: boolean
  auth_required: boolean
}

export interface SurveyData {
  role: Role
  type: ConsultationMode
  name?: string
  position?: string
  union?: string
  email?: string
  company?: string
  countryRegion?: string
  description?: string
}

export type LangCode =
  | 'en' | 'zh' | 'hi' | 'es' | 'ar' | 'fr'
  | 'bn' | 'pt' | 'ru' | 'id' | 'de' | 'mr'
  | 'ja' | 'te' | 'tr' | 'ta' | 'vi' | 'ko'
  | 'ur' | 'th' | 'it' | 'pl' | 'nl' | 'el'
  | 'uk' | 'ro' | 'hr' | 'xh' | 'sw' | 'hu'
  | 'sv'
