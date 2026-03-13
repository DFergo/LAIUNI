import { t } from '../i18n'
import type { LangCode, BrandingConfig } from '../types'

interface Props {
  lang: LangCode
  onAccept: () => void
  onBack: () => void
  branding?: BrandingConfig
  dataProtectionEmail?: string
}

export default function DisclaimerPage({ lang, onAccept, onBack, branding, dataProtectionEmail }: Props) {
  // Replace [DATA_PROTECTION_EMAIL] placeholder in legal text
  const legalBody = (branding?.disclaimer_text || t('disclaimer_legal_body', lang))
    .replace('[DATA_PROTECTION_EMAIL]', dataProtectionEmail || 'dataprotection@uniglobalunion.org')

  return (
    <div className="max-w-4xl mx-auto mt-8 p-6">
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 max-h-[80vh] overflow-y-auto">
        <div className="flex justify-center mb-4">
          <img src={branding?.logo_url || '/uni-logo.png'} alt="UNI Global Union" className="h-[7.5rem]" />
        </div>

        {/* Section 1: What Is This Tool? */}
        <h2 className="text-xl font-semibold text-gray-800 mb-3">{t('disclaimer_what_heading', lang)}</h2>
        <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-line mb-6">
          {t('disclaimer_what_body', lang)}
        </div>

        {/* Section 2: How Your Data Is Handled */}
        <h2 className="text-xl font-semibold text-gray-800 mb-3">{t('disclaimer_data_heading', lang)}</h2>
        <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-line mb-6">
          {t('disclaimer_data_body', lang)}
        </div>

        {/* Section 3: Disclaimer (legal) */}
        <h2 className="text-xl font-semibold text-gray-800 mb-3">{t('disclaimer_legal_heading', lang)}</h2>
        <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-line mb-6">
          {legalBody}
        </div>

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
