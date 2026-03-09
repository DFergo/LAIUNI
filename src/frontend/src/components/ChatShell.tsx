import { t } from '../i18n'
import type { LangCode } from '../types'

interface Props {
  lang: LangCode
  sessionToken: string
}

export default function ChatShell({ lang, sessionToken }: Props) {
  return (
    <div className="max-w-4xl mx-auto mt-8 p-6">
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 text-center">
        <div className="text-sm text-gray-400 mb-4 font-mono">{sessionToken}</div>
        <h2 className="text-xl font-semibold text-gray-800 mb-2">{t('chat_coming_soon', lang)}</h2>
        <p className="text-gray-500">{t('chat_placeholder', lang)}</p>
      </div>
    </div>
  )
}
