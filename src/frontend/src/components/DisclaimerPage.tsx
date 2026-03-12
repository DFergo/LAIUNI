import { t } from '../i18n'
import type { LangCode, BrandingConfig } from '../types'

interface Props {
  lang: LangCode
  onAccept: () => void
  onBack: () => void
  branding?: BrandingConfig
}

export default function DisclaimerPage({ lang, onAccept, onBack, branding }: Props) {
  return (
    <div className="max-w-4xl mx-auto mt-8 p-6">
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <div className="flex justify-center mb-4">
          <img src={branding?.logo_url || '/uni-logo.png'} alt="UNI Global Union" className="h-[7.5rem]" />
        </div>
        <h2 className="text-xl font-semibold text-gray-800 mb-4">{t('disclaimer_title', lang)}</h2>
        <p className="text-gray-600 leading-relaxed mb-6">{branding?.disclaimer_text || t('disclaimer_text', lang)}</p>
        <button
          onClick={onAccept}
          className="w-full bg-uni-blue text-white rounded-lg px-4 py-2.5 font-medium transition-colors hover:opacity-90"
        >
          {t('disclaimer_accept', lang)}
        </button>
        <button
          onClick={onBack}
          className="w-full text-gray-500 text-sm hover:text-gray-700 mt-2"
        >
          &larr; {t('nav_back', lang)}
        </button>
      </div>
    </div>
  )
}
