import { t } from '../i18n'
import type { LangCode, Role, DeploymentConfig } from '../types'

interface Props {
  lang: LangCode
  config: DeploymentConfig
  onSelect: (role: Role) => void
}

export default function RoleSelectPage({ lang, config, onSelect }: Props) {
  const roles: { role: Role; key: string }[] =
    config.frontend_type === 'worker'
      ? [
          { role: 'worker', key: 'role_worker' },
          { role: 'representative', key: 'role_representative' },
        ]
      : [
          { role: 'organizer', key: 'role_organizer' },
          { role: 'officer', key: 'role_officer' },
        ]

  return (
    <div className="max-w-4xl mx-auto mt-8 p-6">
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-2">
          {t('role_select_title', lang)}
        </h2>
        <p className="text-sm text-gray-500 mb-6">
          {t('role_select_subtitle', lang)}
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {roles.map(({ role, key }) => (
            <button
              key={role}
              onClick={() => onSelect(role)}
              className="flex flex-col items-start p-5 rounded-xl border-2 border-gray-200 hover:border-uni-blue hover:bg-blue-50 transition-all text-left group"
            >
              <span className="text-lg font-semibold text-gray-800 group-hover:text-uni-blue">
                {t(key as Parameters<typeof t>[0], lang)}
              </span>
              <span className="text-sm text-gray-500 mt-1">
                {t(`${key}_desc` as Parameters<typeof t>[0], lang)}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
