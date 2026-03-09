import { LANGUAGES } from '../i18n'
import type { LangCode } from '../types'

interface Props {
  onSelect: (lang: LangCode) => void
}

export default function LanguageSelector({ onSelect }: Props) {
  return (
    <div className="max-w-4xl mx-auto mt-8 p-6">
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-1 text-center">Select your language</h2>
        <p className="text-sm text-gray-400 mb-6 text-center">Choose your preferred language to continue</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {LANGUAGES.map(lang => (
            <button
              key={lang.code}
              onClick={() => onSelect(lang.code)}
              className="flex flex-col items-center justify-center px-3 py-4 rounded-lg border border-gray-200 hover:border-uni-blue hover:bg-blue-50 transition-colors"
            >
              <span className="text-sm font-medium text-gray-800">{lang.nativeName}</span>
              <span className="text-xs text-gray-400 mt-0.5">{lang.name}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
