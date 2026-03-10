import { useState, useEffect, useRef } from 'react'
import {
  listRAGDocuments, uploadRAGDocument, deleteRAGDocument, reindexRAG,
  getGlossary, updateGlossary, getOrganizations, updateOrganizations,
  type RAGDocument, type GlossaryTerm, type Organization
} from './api'

export default function RAGTab() {
  const [documents, setDocuments] = useState<RAGDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Knowledge Base state
  const [glossary, setGlossary] = useState<GlossaryTerm[]>([])
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [glossaryDirty, setGlossaryDirty] = useState(false)
  const [orgsDirty, setOrgsDirty] = useState(false)
  const [savingGlossary, setSavingGlossary] = useState(false)
  const [savingOrgs, setSavingOrgs] = useState(false)
  const [editingTerm, setEditingTerm] = useState<GlossaryTerm | null>(null)
  const [editingOrg, setEditingOrg] = useState<Organization | null>(null)

  const refresh = async () => {
    try {
      const [ragData, glossaryData, orgsData] = await Promise.all([
        listRAGDocuments(),
        getGlossary(),
        getOrganizations(),
      ])
      setDocuments(ragData.documents)
      setGlossary(glossaryData.terms)
      setOrganizations(orgsData.organizations)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError('')
    setSuccess('')
    try {
      await uploadRAGDocument(file)
      setSuccess(`Uploaded: ${file.name}`)
      setTimeout(() => setSuccess(''), 3000)
      refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleDelete = async (name: string) => {
    setError('')
    try {
      await deleteRAGDocument(name)
      setDocuments(prev => prev.filter(d => d.name !== name))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const handleReindex = async () => {
    setError('')
    setSuccess('')
    try {
      const result = await reindexRAG()
      setSuccess(`Reindex requested (${result.document_count} documents)`)
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reindex failed')
    }
  }

  // --- Glossary handlers ---
  const handleSaveGlossary = async () => {
    setSavingGlossary(true)
    setError('')
    try {
      const result = await updateGlossary(glossary)
      setGlossary(result.terms)
      setGlossaryDirty(false)
      setSuccess('Glossary saved')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save glossary')
    } finally {
      setSavingGlossary(false)
    }
  }

  const deleteTerm = (term: string) => {
    setGlossary(prev => prev.filter(t => t.term !== term))
    setGlossaryDirty(true)
  }

  const saveTerm = (term: GlossaryTerm, isNew: boolean) => {
    if (isNew) {
      setGlossary(prev => [...prev, term])
    } else {
      setGlossary(prev => prev.map(t => t.term === term.term ? term : t))
    }
    setGlossaryDirty(true)
    setEditingTerm(null)
  }

  // --- Organizations handlers ---
  const handleSaveOrgs = async () => {
    setSavingOrgs(true)
    setError('')
    try {
      const result = await updateOrganizations(organizations)
      setOrganizations(result.organizations)
      setOrgsDirty(false)
      setSuccess('Organizations saved')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save organizations')
    } finally {
      setSavingOrgs(false)
    }
  }

  const deleteOrg = (id: string) => {
    setOrganizations(prev => prev.filter(o => o.id !== id))
    setOrgsDirty(true)
  }

  const saveOrg = (org: Organization, isNew: boolean) => {
    if (isNew) {
      setOrganizations(prev => [...prev, org])
    } else {
      setOrganizations(prev => prev.map(o => o.id === org.id ? org : o))
    }
    setOrgsDirty(true)
    setEditingOrg(null)
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (ts: number) => new Date(ts * 1000).toLocaleString()

  if (loading) return <p className="text-gray-400 text-sm">Loading...</p>

  return (
    <div className="space-y-6">
      {error && <p className="text-sm text-uni-red">{error}</p>}
      {success && <p className="text-sm text-green-600">{success}</p>}

      {/* RAG Documents */}
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800">RAG Documents</h3>
          <div className="flex items-center gap-3">
            <button
              onClick={handleReindex}
              className="border border-gray-300 text-gray-600 rounded-lg px-4 py-1.5 text-sm font-medium transition-colors hover:bg-gray-50"
            >
              Reindex
            </button>
            <label className="bg-uni-blue text-white rounded-lg px-4 py-1.5 text-sm font-medium transition-colors hover:opacity-90 cursor-pointer">
              {uploading ? 'Uploading...' : 'Upload Document'}
              <input
                ref={fileInputRef}
                type="file"
                accept=".md,.txt,.json"
                onChange={handleUpload}
                disabled={uploading}
                className="hidden"
              />
            </label>
          </div>
        </div>
        <p className="text-xs text-gray-400 mb-4">
          Upload .md, .txt, or .json files. These documents are indexed and retrieved via RAG to provide context during conversations.
        </p>
        {documents.length === 0 ? (
          <p className="text-gray-400 text-sm text-center py-6">
            No documents uploaded yet.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left px-2 py-2 font-medium text-gray-600">Name</th>
                <th className="text-right px-2 py-2 font-medium text-gray-600">Size</th>
                <th className="text-right px-2 py-2 font-medium text-gray-600">Modified</th>
                <th className="text-right px-2 py-2 font-medium text-gray-600"></th>
              </tr>
            </thead>
            <tbody>
              {documents.map(doc => (
                <tr key={doc.name} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-2 py-2 font-mono text-gray-800">{doc.name}</td>
                  <td className="px-2 py-2 text-right text-gray-500">{formatSize(doc.size)}</td>
                  <td className="px-2 py-2 text-right text-gray-500">{formatDate(doc.modified)}</td>
                  <td className="px-2 py-2 text-right">
                    <button onClick={() => handleDelete(doc.name)} className="text-xs text-uni-red hover:underline">
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Glossary */}
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-lg font-semibold text-gray-800">Glossary</h3>
          <div className="flex items-center gap-3">
            {glossaryDirty && (
              <button
                onClick={handleSaveGlossary}
                disabled={savingGlossary}
                className="bg-uni-blue text-white rounded-lg px-4 py-1.5 text-sm font-medium transition-colors hover:opacity-90 disabled:opacity-50"
              >
                {savingGlossary ? 'Saving...' : 'Save Glossary'}
              </button>
            )}
            <button
              onClick={() => setEditingTerm({ term: '', short_definition: '', related_standards: [], translations: {} })}
              className="border border-gray-300 text-gray-600 rounded-lg px-4 py-1.5 text-sm font-medium transition-colors hover:bg-gray-50"
            >
              Add Term
            </button>
          </div>
        </div>
        <p className="text-xs text-gray-400 mb-4">
          Curated domain terms injected directly into the LLM context. Ensures consistent terminology and translations across sessions.
        </p>

        {editingTerm && (
          <TermEditor
            term={editingTerm}
            isNew={!glossary.some(t => t.term === editingTerm.term)}
            onSave={saveTerm}
            onCancel={() => setEditingTerm(null)}
          />
        )}

        {glossary.length === 0 ? (
          <p className="text-gray-400 text-sm text-center py-6">No terms defined yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left px-2 py-2 font-medium text-gray-600">Term</th>
                <th className="text-left px-2 py-2 font-medium text-gray-600">Definition</th>
                <th className="text-left px-2 py-2 font-medium text-gray-600">Standards</th>
                <th className="text-center px-2 py-2 font-medium text-gray-600">Langs</th>
                <th className="text-right px-2 py-2 font-medium text-gray-600"></th>
              </tr>
            </thead>
            <tbody>
              {glossary.map(t => (
                <tr key={t.term} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-2 py-2 font-medium text-gray-800">{t.term}</td>
                  <td className="px-2 py-2 text-gray-600 max-w-xs truncate">{t.short_definition}</td>
                  <td className="px-2 py-2 text-gray-500 text-xs">{(t.related_standards || []).join(', ')}</td>
                  <td className="px-2 py-2 text-center text-gray-500 text-xs">
                    {Object.keys(t.translations || {}).length}
                  </td>
                  <td className="px-2 py-2 text-right space-x-2">
                    <button onClick={() => setEditingTerm(t)} className="text-xs text-uni-blue hover:underline">
                      Edit
                    </button>
                    <button onClick={() => deleteTerm(t.term)} className="text-xs text-uni-red hover:underline">
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Organizations Directory */}
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-lg font-semibold text-gray-800">Organizations Directory</h3>
          <div className="flex items-center gap-3">
            {orgsDirty && (
              <button
                onClick={handleSaveOrgs}
                disabled={savingOrgs}
                className="bg-uni-blue text-white rounded-lg px-4 py-1.5 text-sm font-medium transition-colors hover:opacity-90 disabled:opacity-50"
              >
                {savingOrgs ? 'Saving...' : 'Save Organizations'}
              </button>
            )}
            <button
              onClick={() => setEditingOrg({ id: '', name: '', type: 'GUF', scope: 'global', description: '' })}
              className="border border-gray-300 text-gray-600 rounded-lg px-4 py-1.5 text-sm font-medium transition-colors hover:bg-gray-50"
            >
              Add Organization
            </button>
          </div>
        </div>
        <p className="text-xs text-gray-400 mb-4">
          Curated list of unions, federations, and institutions. The LLM uses this for referrals — it does not invent organization names.
        </p>

        {editingOrg && (
          <OrgEditor
            org={editingOrg}
            isNew={!organizations.some(o => o.id === editingOrg.id)}
            onSave={saveOrg}
            onCancel={() => setEditingOrg(null)}
          />
        )}

        {organizations.length === 0 ? (
          <p className="text-gray-400 text-sm text-center py-6">No organizations defined yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left px-2 py-2 font-medium text-gray-600">Name</th>
                <th className="text-left px-2 py-2 font-medium text-gray-600">Type</th>
                <th className="text-left px-2 py-2 font-medium text-gray-600">Scope</th>
                <th className="text-left px-2 py-2 font-medium text-gray-600">Sectors</th>
                <th className="text-right px-2 py-2 font-medium text-gray-600"></th>
              </tr>
            </thead>
            <tbody>
              {organizations.map(o => (
                <tr key={o.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-2 py-2 text-gray-800">
                    <span className="font-medium">{o.name}</span>
                    {o.acronym && <span className="text-gray-400 ml-1">({o.acronym})</span>}
                  </td>
                  <td className="px-2 py-2 text-gray-500 text-xs uppercase">{o.type}</td>
                  <td className="px-2 py-2 text-gray-500 text-xs">{o.scope}{o.region ? ` — ${o.region}` : ''}</td>
                  <td className="px-2 py-2 text-gray-500 text-xs max-w-xs truncate">
                    {(o.sectors || []).join(', ')}
                  </td>
                  <td className="px-2 py-2 text-right space-x-2">
                    <button onClick={() => setEditingOrg(o)} className="text-xs text-uni-blue hover:underline">
                      Edit
                    </button>
                    <button onClick={() => deleteOrg(o.id)} className="text-xs text-uni-red hover:underline">
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// --- Term Editor Modal ---
function TermEditor({ term, isNew, onSave, onCancel }: {
  term: GlossaryTerm
  isNew: boolean
  onSave: (t: GlossaryTerm, isNew: boolean) => void
  onCancel: () => void
}) {
  const [data, setData] = useState<GlossaryTerm>({ ...term })
  const [standards, setStandards] = useState((term.related_standards || []).join(', '))
  const [transText, setTransText] = useState(
    Object.entries(term.translations || {}).map(([k, v]) => `${k}: ${v}`).join('\n')
  )

  const handleSave = () => {
    const parsed: GlossaryTerm = {
      ...data,
      related_standards: standards.split(',').map(s => s.trim()).filter(Boolean),
      translations: Object.fromEntries(
        transText.split('\n').filter(l => l.includes(':')).map(l => {
          const [lang, ...rest] = l.split(':')
          return [lang.trim(), rest.join(':').trim()]
        })
      ),
    }
    onSave(parsed, isNew)
  }

  return (
    <div className="border border-uni-blue rounded-lg p-4 mb-4 bg-blue-50/30">
      <h4 className="text-sm font-semibold text-gray-700 mb-3">{isNew ? 'Add Term' : 'Edit Term'}</h4>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Term (English)</label>
          <input type="text" value={data.term} disabled={!isNew}
            onChange={e => setData({ ...data, term: e.target.value })}
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none disabled:bg-gray-100" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Related Standards (comma-separated)</label>
          <input type="text" value={standards}
            onChange={e => setStandards(e.target.value)}
            placeholder="ILO Convention 87, ILO Convention 98"
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
        </div>
      </div>
      <div className="mb-3">
        <label className="block text-xs font-medium text-gray-600 mb-1">Definition</label>
        <textarea value={data.short_definition}
          onChange={e => setData({ ...data, short_definition: e.target.value })}
          rows={2}
          className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none resize-none" />
      </div>
      <div className="mb-3">
        <label className="block text-xs font-medium text-gray-600 mb-1">Translations (one per line: <code className="text-xs">lang: term</code>)</label>
        <textarea value={transText}
          onChange={e => setTransText(e.target.value)}
          rows={3} placeholder={"es: Libertad sindical\nfr: Liberté syndicale"}
          className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm font-mono focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none resize-none" />
      </div>
      <div className="flex gap-2">
        <button onClick={handleSave}
          className="bg-uni-blue text-white rounded-lg px-4 py-1.5 text-sm font-medium hover:opacity-90">
          {isNew ? 'Add' : 'Update'}
        </button>
        <button onClick={onCancel}
          className="border border-gray-300 text-gray-600 rounded-lg px-4 py-1.5 text-sm font-medium hover:bg-gray-50">
          Cancel
        </button>
      </div>
    </div>
  )
}

// --- Organization Editor Modal ---
function OrgEditor({ org, isNew, onSave, onCancel }: {
  org: Organization
  isNew: boolean
  onSave: (o: Organization, isNew: boolean) => void
  onCancel: () => void
}) {
  const [data, setData] = useState<Organization>({ ...org })
  const [sectors, setSectors] = useState((org.sectors || []).join(', '))

  const handleSave = () => {
    const parsed: Organization = {
      ...data,
      id: data.id || data.name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
      sectors: sectors.split(',').map(s => s.trim()).filter(Boolean),
    }
    onSave(parsed, isNew)
  }

  return (
    <div className="border border-uni-blue rounded-lg p-4 mb-4 bg-blue-50/30">
      <h4 className="text-sm font-semibold text-gray-700 mb-3">{isNew ? 'Add Organization' : 'Edit Organization'}</h4>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Name</label>
          <input type="text" value={data.name}
            onChange={e => setData({ ...data, name: e.target.value })}
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Acronym</label>
          <input type="text" value={data.acronym || ''}
            onChange={e => setData({ ...data, acronym: e.target.value })}
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Type</label>
          <select value={data.type} onChange={e => setData({ ...data, type: e.target.value })}
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none">
            <option value="GUF">GUF (Global Union Federation)</option>
            <option value="ETUF">ETUF (European TU Federation)</option>
            <option value="confederation">Confederation</option>
            <option value="national_union">National Union</option>
            <option value="sector">Sector</option>
            <option value="international_body">International Body</option>
            <option value="certification_body">Certification Body</option>
            <option value="ngo">NGO</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Scope</label>
          <select value={data.scope} onChange={e => setData({ ...data, scope: e.target.value })}
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none">
            <option value="global">Global</option>
            <option value="regional">Regional</option>
            <option value="national">National</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Region</label>
          <input type="text" value={data.region || ''}
            onChange={e => setData({ ...data, region: e.target.value })}
            placeholder="e.g. Europe, Latin America"
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Sectors (comma-separated)</label>
          <input type="text" value={sectors}
            onChange={e => setSectors(e.target.value)}
            placeholder="manufacturing, forestry, paper"
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Contact URL</label>
          <input type="url" value={data.contact_url || ''}
            onChange={e => setData({ ...data, contact_url: e.target.value })}
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
        </div>
      </div>
      <div className="mb-3">
        <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
        <textarea value={data.description}
          onChange={e => setData({ ...data, description: e.target.value })}
          rows={2}
          className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none resize-none" />
      </div>
      <div className="mb-3">
        <label className="block text-xs font-medium text-gray-600 mb-1">Note (internal, not shown to users)</label>
        <input type="text" value={data.note || ''}
          onChange={e => setData({ ...data, note: e.target.value })}
          placeholder="e.g. Do not recommend direct contact"
          className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-uni-blue focus:border-transparent outline-none" />
      </div>
      <div className="flex gap-2">
        <button onClick={handleSave}
          className="bg-uni-blue text-white rounded-lg px-4 py-1.5 text-sm font-medium hover:opacity-90">
          {isNew ? 'Add' : 'Update'}
        </button>
        <button onClick={onCancel}
          className="border border-gray-300 text-gray-600 rounded-lg px-4 py-1.5 text-sm font-medium hover:bg-gray-50">
          Cancel
        </button>
      </div>
    </div>
  )
}
