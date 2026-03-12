import { t } from '../i18n'
import type { LangCode, Role } from '../types'

interface Props {
  lang: LangCode
  role: Role
  onContinue: () => void
}

export default function InstructionsPage({ lang, role, onContinue }: Props) {
  const titleKey = `instructions_${role}_title` as Parameters<typeof t>[0]
  const textKey = `instructions_${role}_text` as Parameters<typeof t>[0]

  return (
    <div className="max-w-4xl mx-auto mt-8 p-6">
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <div className="flex justify-center mb-4">
          <img src="/uni-logo.png" alt="UNI Global Union" className="h-[7.5rem]" />
        </div>
        <h2 className="text-xl font-semibold text-gray-800 mb-4">
          {t(titleKey, lang)}
        </h2>
        <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-line mb-6">
          {t(textKey, lang)}
        </div>
        <button
          onClick={onContinue}
          className="w-full bg-uni-blue text-white rounded-lg px-4 py-2.5 font-medium transition-colors hover:opacity-90"
        >
          {t('instructions_continue', lang)}
        </button>
      </div>
    </div>
  )
}
