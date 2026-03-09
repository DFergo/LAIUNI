import { t } from '../i18n'
import type { LangCode } from '../types'

interface Props {
  lang: LangCode
  onAccept: () => void
}

export default function DisclaimerPage({ lang, onAccept }: Props) {
  return (
    <div className="max-w-4xl mx-auto mt-8 p-6">
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">{t('disclaimer_title', lang)}</h2>
        <p className="text-gray-600 leading-relaxed mb-6">{t('disclaimer_text', lang)}</p>
        <button
          onClick={onAccept}
          className="w-full bg-uni-blue text-white rounded-lg px-4 py-2.5 font-medium transition-colors hover:opacity-90"
        >
          {t('disclaimer_accept', lang)}
        </button>
      </div>
    </div>
  )
}
