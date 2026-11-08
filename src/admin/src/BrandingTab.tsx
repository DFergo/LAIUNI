import { useEffect, useState } from 'react'
import BrandingEditor from './BrandingEditor'
import {
  getGlobalBranding, updateGlobalBranding, resetGlobalBranding, uploadBrandLogo, deleteBrandLogo,
  type BrandingCatalog,
} from './api'

// Global branding (Sprint 43): the organization's names, colours and logos for every frontend
// that does not set its own (Frontends → Branding).

interface Props {
  onChanged: () => void   // the admin panel re-reads the tokens and repaints itself
}

export default function BrandingTab({ onChanged }: Props) {
  const [catalog, setCatalog] = useState<BrandingCatalog | null>(null)
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    getGlobalBranding().then(setCatalog).catch(e => setError((e as Error).message))
  }, [])

  const dirty = Object.keys(edits).length > 0

  const apply = (c: BrandingCatalog, note: string) => {
    setCatalog(c); setEdits({}); setMessage(note); setError(''); onChanged()
  }

  const save = async () => {
    setSaving(true); setMessage(''); setError('')
    try { apply(await updateGlobalBranding(edits), 'Saved. Every frontend picks it up within seconds.') }
    catch (e) { setError((e as Error).message) }
    finally { setSaving(false) }
  }

  const reset = async () => {
    if (!window.confirm('Remove every global branding value and logo and go back to the defaults? Frontends with their own branding keep it.')) return
    setSaving(true); setMessage(''); setError('')
    try { apply(await resetGlobalBranding(), 'Back to the defaults.') }
    catch (e) { setError((e as Error).message) }
    finally { setSaving(false) }
  }

  if (!catalog) return <p className="text-gray-400 text-sm">{error || 'Loading...'}</p>

  return (
    <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-800">Branding</h2>
        <p className="text-xs text-gray-400">
          The organization behind this installation: its name, the tool's name, colours and logos. Applies to the admin panel
          and to every frontend; a frontend can override any of it under Frontends → Branding.
        </p>
      </div>
      <BrandingEditor
        scope={null}
        catalog={catalog}
        edits={edits}
        onEdit={(name, value) => setEdits(e => ({ ...e, [name]: value }))}
        onUploadLogo={async (slot, file) => { setCatalog(await uploadBrandLogo(null, slot, file)); setMessage('Logo saved.'); onChanged() }}
        onDeleteLogo={async slot => { setCatalog(await deleteBrandLogo(null, slot)); setMessage('Logo removed.'); onChanged() }}
      />
      {error && <p className="text-sm text-brand-accent">{error}</p>}
      {message && <p className="text-sm text-green-700">{message}</p>}
      <div className="flex items-center gap-3">
        <button onClick={save} disabled={!dirty || saving}
          className="bg-brand-primary text-brand-on-primary rounded-lg px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50">
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button onClick={reset} disabled={saving}
          className="text-sm text-brand-accent border border-brand-accent rounded-lg px-4 py-2 hover:bg-red-50 disabled:opacity-50">
          Reset to defaults
        </button>
      </div>
    </div>
  )
}
