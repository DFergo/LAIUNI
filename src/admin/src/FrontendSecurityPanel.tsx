import { useState } from 'react'
import { updateFrontend, type Frontend, type FrontendCredentials } from './api'

// 32 random bytes as hex (64 chars) — must also be set as HRDD_BACKEND_SECRET on the frontend.
export function generateSecret(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
}

// "Name: value" per line → object. Blank lines ignored.
export function parseHeaders(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const i = line.indexOf(':')
    if (i <= 0) continue
    const name = line.slice(0, i).trim()
    const value = line.slice(i + 1).trim()
    if (name && value) out[name] = value
  }
  return out
}

const inputCls = 'w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm font-mono focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none'

// Secret + extra-headers inputs, shared by the register form and the per-frontend panel.
export function CredentialFields({ secret, setSecret, headers, setHeaders }: {
  secret: string; setSecret: (v: string) => void
  headers: string; setHeaders: (v: string) => void
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Signing secret</label>
        <div className="flex gap-2">
          <input type="text" value={secret} onChange={e => setSecret(e.target.value)}
            placeholder="≥ 32 characters — same value as HRDD_BACKEND_SECRET on the frontend"
            className={inputCls} autoComplete="off" spellCheck={false} />
          <button type="button" onClick={() => setSecret(generateSecret())}
            className="text-xs px-3 py-1 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 font-medium whitespace-nowrap">
            Generate
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-1">Copy it now — it is never shown again.</p>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Extra headers (optional)</label>
        <textarea value={headers} onChange={e => setHeaders(e.target.value)} rows={2}
          placeholder={'CF-Access-Client-Id: …\nCF-Access-Client-Secret: …'}
          className={inputCls} spellCheck={false} />
        <p className="text-xs text-gray-400 mt-1">One "Name: value" per line (e.g. Cloudflare Access service token). Write-only.</p>
      </div>
    </div>
  )
}

export function SigningBadge({ f }: { f: Frontend }) {
  return f.signing_enabled
    ? <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-green-50 text-green-700 border border-green-200">signed</span>
    : <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200" title="Legacy unsigned protocol — set a signing secret">unsigned</span>
}

export default function FrontendSecurityPanel({ f, onSaved }: { f: Frontend; onSaved: () => void }) {
  const [url, setUrl] = useState(f.url)
  const [secret, setSecret] = useState('')
  const [headers, setHeaders] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const save = async (data: FrontendCredentials & { url?: string }, done: string) => {
    setBusy(true); setErr(''); setMsg('')
    try {
      await updateFrontend(f.id, data)
      setSecret(''); setHeaders('')
      setMsg(done)
      onSaved()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  const urlChanged = url.trim().replace(/\/+$/, '') !== f.url

  // URL + credentials go in ONE update: moving a frontend to signing changes both
  // (backend-port URL + secret), and the save is verified with the final pair.
  const saveBoth = () => {
    const data: FrontendCredentials & { url?: string } = {}
    if (urlChanged) data.url = url.trim()
    if (secret.trim()) data.signing_secret = secret.trim()
    if (headers.trim()) data.extra_headers = parseHeaders(headers)
    if (!Object.keys(data).length) return
    save(data, 'Saved — the frontend accepted the new credentials.')
  }

  return (
    <div className="mt-3 border-t border-gray-100 pt-3 space-y-3">
      <div className="text-xs text-gray-500">
        Signing: <strong>{f.signing_enabled ? 'enabled' : 'disabled (legacy unsigned protocol)'}</strong>
        {' · '}Extra headers: <strong>{f.extra_header_names?.length ? f.extra_header_names.join(', ') : 'none'}</strong>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Backend-port URL</label>
        <input type="text" value={url} onChange={e => setUrl(e.target.value)} spellCheck={false}
          className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm font-mono focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
        <p className="text-xs text-gray-400 mt-1">When enabling signing on an existing frontend, change this to its backend port in the same save.</p>
      </div>
      <CredentialFields secret={secret} setSecret={setSecret} headers={headers} setHeaders={setHeaders} />
      <p className="text-xs text-gray-400">
        Saving checks the credentials against the frontend first. To rotate without downtime: set the new value as
        HRDD_BACKEND_SECRET on the frontend and the old one as HRDD_BACKEND_SECRET_PREVIOUS, save here, then remove the previous one.
      </p>
      <div className="flex gap-2">
        <button onClick={saveBoth} disabled={busy || (!urlChanged && !secret.trim() && !headers.trim())}
          className="bg-uni-blue text-white rounded-lg px-4 py-1.5 text-sm font-medium hover:opacity-90 disabled:opacity-50">
          {busy ? '...' : 'Save credentials'}
        </button>
        {!!f.extra_header_names?.length && (
          <button onClick={() => save({ extra_headers: {} }, 'Extra headers removed.')} disabled={busy}
            className="text-xs px-3 py-1 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 font-medium">
            Remove extra headers
          </button>
        )}
      </div>
      {msg && <p className="text-xs text-green-700">{msg}</p>}
      {err && <p className="text-xs text-uni-red">{err}</p>}
    </div>
  )
}
