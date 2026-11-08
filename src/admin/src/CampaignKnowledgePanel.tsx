import { useEffect, useRef, useState } from 'react'
import {
  getFrontendKnowledge, updateFrontendKnowledge,
  type FrontendKnowledge, type GlossaryTerm, type KnowledgeMode, type Organization,
} from './api'

type Kind = 'glossary' | 'organizations'

interface Props {
  frontendId: string
  globalTerms: GlossaryTerm[]
  globalOrganizations: Organization[]
  globalGlossaryEnabled: boolean
  globalOrganizationsEnabled: boolean
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

const LABELS: Record<Kind, { title: string; key: 'terms' | 'organizations'; unit: string }> = {
  glossary: { title: 'Glossary', key: 'terms', unit: 'terms' },
  organizations: { title: 'Organizations', key: 'organizations', unit: 'organizations' },
}

function validate(kind: Kind, data: unknown): GlossaryTerm[] | Organization[] {
  const key = LABELS[kind].key
  const items = (data as Record<string, unknown>)?.[key]
  if (!Array.isArray(items)) throw new Error(`Invalid format: JSON must have a "${key}" array.`)
  for (const it of items) {
    const ok = kind === 'glossary' ? it?.term : it?.name && it?.type && it?.country
    if (!ok) throw new Error(`Invalid entry: ${JSON.stringify(it).slice(0, 80)}`)
  }
  return items
}

// Per-frontend glossary and organizations: follow the global list, switch off,
// or use an own list (e.g. only the campaign's two reference unions).
export default function CampaignKnowledgePanel(props: Props) {
  const { frontendId, onError, onSuccess } = props
  const [state, setState] = useState<FrontendKnowledge | null>(null)
  const uploadRefs = useRef<Record<Kind, HTMLInputElement | null>>({ glossary: null, organizations: null })

  useEffect(() => {
    getFrontendKnowledge(frontendId).then(setState).catch(() => onError('Failed to load glossary/organizations settings'))
  }, [frontendId])

  const save = async (kind: Kind, mode: KnowledgeMode, items?: GlossaryTerm[] | Organization[], msg?: string) => {
    try {
      setState(await updateFrontendKnowledge(frontendId, kind, mode, items))
      onSuccess(msg || `${LABELS[kind].title}: ${mode === 'custom' ? 'own list' : mode}`)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Save failed')
    }
  }

  const upload = async (kind: Kind, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const items = validate(kind, JSON.parse(await file.text()))
      await save(kind, 'custom', items, `${LABELS[kind].title}: own list with ${items.length} ${LABELS[kind].unit}`)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Invalid JSON file')
    } finally {
      const ref = uploadRefs.current[kind]
      if (ref) ref.value = ''
    }
  }

  const download = (kind: Kind, items: unknown[]) => {
    const blob = new Blob([JSON.stringify({ [LABELS[kind].key]: items }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${kind}-${frontendId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (!state) return null

  const row = (kind: Kind) => {
    const { title, unit } = LABELS[kind]
    const entry = state[kind]
    const own = (kind === 'glossary' ? state.glossary.terms : state.organizations.organizations) as unknown[]
    const global = kind === 'glossary' ? props.globalTerms : props.globalOrganizations
    const globalOn = kind === 'glossary' ? props.globalGlossaryEnabled : props.globalOrganizationsEnabled
    const hint = entry.mode === 'off' ? 'not used in this frontend'
      : entry.mode === 'custom' ? `own list: ${own.length} ${unit}`
      : globalOn ? `global list: ${global.length} ${unit}` : 'global list is switched off'
    return (
      <div key={kind} className="flex flex-wrap items-center gap-2 text-xs">
        <span className="w-24 font-medium text-gray-700">{title}</span>
        <select
          value={entry.mode}
          onChange={e => {
            const mode = e.target.value as KnowledgeMode
            // First own list: start from the global one, ready to trim
            if (mode === 'custom' && own.length === 0) save(kind, mode, global, `${title}: own list started from the global one`)
            else save(kind, mode)
          }}
          className="border border-gray-300 rounded-lg px-2 py-1 text-xs"
        >
          <option value="global">Global</option>
          <option value="off">Off</option>
          <option value="custom">Own list</option>
        </select>
        <span className="text-gray-400">{hint}</span>
        {entry.mode === 'custom' && (
          <span className="flex items-center gap-2 ml-auto">
            <button
              onClick={() => save(kind, 'custom', global, `${title}: copied ${global.length} ${unit} from global`)}
              className="border border-gray-300 text-gray-600 rounded-lg px-2 py-1 hover:bg-gray-50"
            >
              Copy from global
            </button>
            <button
              onClick={() => download(kind, own)}
              className="border border-gray-300 text-gray-600 rounded-lg px-2 py-1 hover:bg-gray-50"
            >
              Download JSON
            </button>
            <label className="bg-brand-primary text-brand-on-primary rounded-lg px-2 py-1 hover:opacity-90 cursor-pointer">
              Upload JSON
              <input
                ref={el => { uploadRefs.current[kind] = el }}
                type="file"
                accept=".json"
                onChange={e => upload(kind, e)}
                className="hidden"
              />
            </label>
          </span>
        )}
      </div>
    )
  }

  return (
    <div className="mt-4 pt-3 border-t border-gray-100">
      <p className="text-xs font-medium text-gray-600 mb-2">Glossary and organizations</p>
      <div className="space-y-2 pl-1">
        {row('glossary')}
        {row('organizations')}
      </div>
      <p className="text-xs text-gray-400 mt-1 pl-1">
        Own list: start from the global one (Copy from global), download it, keep only what this campaign needs, upload it.
      </p>
    </div>
  )
}
