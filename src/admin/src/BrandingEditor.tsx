import { useEffect, useState } from 'react'
import { fetchBrandLogo, type BrandingCatalog, type BrandToken } from './api'
import { channels } from './brand'

// Edits the branding tokens (names, colours) and the logos of one level: the global catalog
// (scope = null) or one frontend (scope = its id; what it leaves unset inherits the global value).
// Token edits are controlled by the parent: `edits` maps name -> value, '' = back to inherited/default.
// Logos act at once (upload / remove).

interface Props {
  scope: string | null
  catalog: BrandingCatalog
  edits: Record<string, string>
  onEdit: (name: string, value: string) => void
  onUploadLogo: (slot: string, file: File) => Promise<void>
  onDeleteLogo: (slot: string) => Promise<void>
  hideTokens?: string[]          // tokens edited elsewhere in the panel
  headerLogoMode?: 'white' | 'color'
  onHeaderLogoMode?: (mode: 'white' | 'color') => void
}

const SLOT_LABELS: Record<string, string> = {
  header: 'Top bar',
  page: 'Pages (language, disclaimer, instructions)',
  chat_bg: 'Chat background',
}

const inputClass = 'w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-primary focus:border-transparent outline-none'

function isLight(hex: string): boolean {
  const [r, g, b] = channels(hex).split(' ').map(Number)
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.5
}

export default function BrandingEditor({ scope, catalog, edits, onEdit, onUploadLogo, onDeleteLogo, hideTokens = [], headerLogoMode, onHeaderLogoMode }: Props) {
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [previews, setPreviews] = useState<Record<string, string | null>>({})

  const ownLevel = scope ? 'frontend' : 'global'
  const byName: Record<string, BrandToken> = Object.fromEntries(catalog.tokens.map(t => [t.name, t]))
  // What the token shows once the pending edits are saved
  const effective = (name: string) => {
    const edited = edits[name]
    return edited === undefined ? byName[name].value : edited === '' ? byName[name].inherited : edited
  }
  const isOwn = (t: BrandToken) => (edits[t.name] !== undefined ? edits[t.name] !== '' : t.source === ownLevel)

  // Logo previews (auth-gated, fetched as blobs); reloaded when a logo changes.
  const logoKey = JSON.stringify(Object.entries(catalog.logos).map(([k, l]) => [k, l.source, l.uploaded, l.has_white]))
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const next: Record<string, string | null> = {}
      for (const [slot, logo] of Object.entries(catalog.logos)) {
        next[`${slot}/color`] = logo.uploaded ? await fetchBrandLogo(scope, slot, 'color') : null
        next[`${slot}/white`] = logo.uploaded && logo.has_white ? await fetchBrandLogo(scope, slot, 'white') : null
      }
      if (!cancelled) setPreviews(next)
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logoKey, scope])

  const run = async (slot: string, fn: () => Promise<void>) => {
    setBusy(slot); setError('')
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  const primary = effective('color_primary')
  const onPrimary = effective('color_on_primary')
  const whiteOnBar = headerLogoMode !== 'color' && isLight(onPrimary)
  const headerPreview = (whiteOnBar && previews['header/white']) || previews['header/color'] || null
  const slotPreview = (slot: string) => (slot === 'header' ? headerPreview : previews[`${slot}/color`])

  const field = (t: BrandToken) => {
    const own = isOwn(t)
    const shown = edits[t.name] ?? (t.source === ownLevel ? t.value : '')
    const colorValue = /^#[0-9a-fA-F]{6}$/.test(effective(t.name)) ? effective(t.name) : '#000000'
    return (
      <div key={t.name}>
        <div className="flex items-center justify-between mb-1">
          <label className="block text-xs font-medium text-gray-600">{t.label}</label>
          <span className="text-[11px] text-gray-400">
            {own ? (scope ? 'own' : 'changed') : (scope ? 'inherited' : 'default')}
            {own && (
              <button type="button" onClick={() => onEdit(t.name, '')} className="ml-2 text-brand-primary hover:underline">
                {scope ? 'use global' : 'use default'}
              </button>
            )}
          </span>
        </div>
        {t.kind === 'color' ? (
          <div className="flex items-center gap-2">
            <input type="color" value={colorValue} onChange={e => onEdit(t.name, e.target.value.toUpperCase())}
              className="h-8 w-10 rounded border border-gray-300 cursor-pointer p-0.5 bg-white" />
            <input type="text" value={shown} placeholder={t.inherited} maxLength={7}
              onChange={e => onEdit(t.name, e.target.value.trim())} className={`${inputClass} font-mono`} />
          </div>
        ) : (
          <input type="text" value={shown} placeholder={t.inherited}
            onChange={e => onEdit(t.name, e.target.value)} className={inputClass} />
        )}
        <p className="text-[11px] text-gray-400 mt-0.5">{t.used_in}</p>
      </div>
    )
  }

  const shownTokens = catalog.tokens.filter(t => !hideTokens.includes(t.name))

  return (
    <div className="space-y-4">
      {/* Live preview of the pending values */}
      <div className="rounded-lg overflow-hidden border border-gray-200">
        <div className="px-4 py-2.5 flex items-center justify-between" style={{ background: primary, color: onPrimary }}>
          <div className="flex items-center gap-3">
            {headerPreview && <img src={headerPreview} alt="" className="h-6" />}
            <span className="font-semibold text-sm">{effective('tool_name')}</span>
          </div>
          <span className="text-xs opacity-75">{effective('org_name')}</span>
        </div>
        <div className="bg-gray-50 px-4 py-3 flex items-center gap-3">
          <span className="text-xs rounded-lg px-3 py-1.5 font-medium" style={{ background: primary, color: onPrimary }}>Button</span>
          <span className="text-xs" style={{ color: primary }}>Link</span>
          <span className="text-xs" style={{ color: effective('color_accent') }}>Error or alert</span>
          <span className="text-xs rounded px-2 py-1 text-white" style={{ background: effective('color_dark') }}>Admin header</span>
        </div>
      </div>

      {catalog.warnings.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-800 space-y-0.5">
          {catalog.warnings.map(w => <p key={w}>{w}</p>)}
          <p className="text-amber-600">Readability warnings reflect the saved colours.</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">{shownTokens.filter(t => t.kind === 'text').map(field)}</div>
      <div className="grid grid-cols-2 gap-3">{shownTokens.filter(t => t.kind === 'color').map(field)}</div>

      {/* Logos */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-600">
          Logos <span className="font-normal text-gray-400">(PNG / WEBP / JPG, max 2 MB; a transparent PNG also gets a white version)</span>
        </p>
        {error && <p className="text-xs text-brand-accent">{error}</p>}
        <div className="grid grid-cols-3 gap-3">
          {Object.entries(catalog.logos).map(([slot, logo]) => {
            const mine = logo.source === ownLevel
            const preview = slotPreview(slot)
            return (
              <div key={slot} className="border border-gray-200 rounded-lg p-3 space-y-2">
                <p className="text-xs font-medium text-gray-600">{SLOT_LABELS[slot] ?? slot}</p>
                <div className="rounded-lg p-2 flex items-center justify-center h-16" style={{ background: slot === 'header' ? primary : '#F3F4F6' }}>
                  {preview
                    ? <img src={preview} alt="" className="max-h-12 max-w-full object-contain" />
                    : <span className="text-[11px] text-gray-400 text-center">{logo.uploaded ? '…' : 'bundled logo'}</span>}
                </div>
                <p className="text-[11px] text-gray-400">
                  {mine ? 'Own logo' : logo.source === 'global' ? 'Inherits the global logo' : 'Not set'}
                  {slot === 'header' && logo.uploaded && !logo.has_white && ' · no transparency, shown in colour'}
                </p>
                <div className="flex items-center gap-2">
                  <label className={`text-xs px-2 py-1 rounded-lg border cursor-pointer border-brand-primary text-brand-primary hover:bg-brand-primary/5 ${busy === slot ? 'opacity-50 pointer-events-none' : ''}`}>
                    {mine ? 'Replace' : 'Upload'}
                    <input type="file" accept=".png,.webp,.jpg,.jpeg" className="hidden"
                      onChange={e => { const f = e.target.files?.[0]; if (f) run(slot, () => onUploadLogo(slot, f)); e.target.value = '' }} />
                  </label>
                  {mine && (
                    <button type="button" disabled={busy === slot} onClick={() => run(slot, () => onDeleteLogo(slot))}
                      className="text-xs px-2 py-1 rounded-lg border border-brand-accent text-brand-accent hover:bg-red-50 disabled:opacity-50">
                      {scope ? 'Use global' : 'Remove'}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
        {onHeaderLogoMode && catalog.logos.header?.uploaded && catalog.logos.header.has_white && (
          <div className="flex items-center gap-4 text-xs text-gray-600">
            <span className="font-medium">Top bar logo:</span>
            <label className="flex items-center gap-1 cursor-pointer">
              <input type="radio" checked={headerLogoMode !== 'color'} onChange={() => onHeaderLogoMode('white')} /> White
            </label>
            <label className="flex items-center gap-1 cursor-pointer">
              <input type="radio" checked={headerLogoMode === 'color'} onChange={() => onHeaderLogoMode('color')} /> Original colour
            </label>
            <span className="text-gray-400">(applied on Save; white is used only while the text on the primary colour is light)</span>
          </div>
        )}
      </div>

      {catalog.fixed.map(f => (
        <p key={f.name} className="text-[11px] text-gray-400">Copyright line: “© 2026 {f.value}” — {f.note}</p>
      ))}
    </div>
  )
}
