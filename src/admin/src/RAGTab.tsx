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
  const glossaryUploadRef = useRef<HTMLInputElement>(null)
  const orgsUploadRef = useRef<HTMLInputElement>(null)
  const [glossaryExpanded, setGlossaryExpanded] = useState(false)
  const [orgsExpanded, setOrgsExpanded] = useState(false)

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

  // --- RAG handlers ---
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
      const msg = result.node_count
        ? `Indexed: ${result.document_count} documents → ${result.node_count} chunks`
        : `Reindex: ${result.document_count} documents`
      setSuccess(msg)
      setTimeout(() => setSuccess(''), 5000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reindex failed')
    }
  }

  // --- Knowledge Base handlers ---
  const downloadJSON = (data: unknown, filename: string) => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleGlossaryUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      // Validate structure
      if (!Array.isArray(data.terms)) {
        throw new Error('Invalid format: JSON must have a "terms" array. Download the template for reference.')
      }
      for (const t of data.terms) {
        if (!t.term) {
          throw new Error(`Invalid term: each entry needs at least a "term" field. Problem with: ${JSON.stringify(t).slice(0, 80)}`)
        }
      }
      const result = await updateGlossary(data.terms)
      setGlossary(result.terms)
      setSuccess(`Glossary updated: ${result.terms.length} terms`)
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid JSON file')
    } finally {
      if (glossaryUploadRef.current) glossaryUploadRef.current.value = ''
    }
  }

  const handleOrgsUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      if (!Array.isArray(data.organizations)) {
        throw new Error('Invalid format: JSON must have an "organizations" array. Download the template for reference.')
      }
      for (const o of data.organizations) {
        if (!o.name || !o.type || !o.country) {
          throw new Error(`Invalid entry: each organization needs "name", "type", and "country". Problem with: ${JSON.stringify(o).slice(0, 80)}`)
        }
      }
      const result = await updateOrganizations(data.organizations)
      setOrganizations(result.organizations)
      setSuccess(`Organizations updated: ${result.organizations.length} entries`)
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid JSON file')
    } finally {
      if (orgsUploadRef.current) orgsUploadRef.current.value = ''
    }
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
          <p className="text-gray-400 text-sm text-center py-6">No documents uploaded yet.</p>
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
          <h3 className="text-lg font-semibold text-gray-800">
            Glossary
            <span className="text-sm font-normal text-gray-400 ml-2">({glossary.length} terms)</span>
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={() => downloadJSON({ terms: glossary }, 'glossary.json')}
              className="border border-gray-300 text-gray-600 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors hover:bg-gray-50"
            >
              Download JSON
            </button>
            <label className="bg-uni-blue text-white rounded-lg px-3 py-1.5 text-sm font-medium transition-colors hover:opacity-90 cursor-pointer">
              Upload JSON
              <input
                ref={glossaryUploadRef}
                type="file"
                accept=".json"
                onChange={handleGlossaryUpload}
                className="hidden"
              />
            </label>
          </div>
        </div>
        <p className="text-xs text-gray-400 mb-3">
          Domain terms injected into every session for consistent terminology and translations.
          Download the current file, edit it, and upload the updated version.
        </p>

        {glossary.length > 0 && (
          <>
            <button
              onClick={() => setGlossaryExpanded(!glossaryExpanded)}
              className="text-xs text-uni-blue hover:underline mb-2"
            >
              {glossaryExpanded ? 'Hide terms' : `Show all ${glossary.length} terms`}
            </button>
            {glossaryExpanded && (
              <table className="w-full text-sm mt-2">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left px-2 py-2 font-medium text-gray-600">Term</th>
                    <th className="text-left px-2 py-2 font-medium text-gray-600">Definition</th>
                    <th className="text-left px-2 py-2 font-medium text-gray-600">Translations</th>
                  </tr>
                </thead>
                <tbody>
                  {glossary.map(t => (
                    <tr key={t.term} className="border-b border-gray-100">
                      <td className="px-2 py-2 font-medium text-gray-800 whitespace-nowrap">{t.term}</td>
                      <td className="px-2 py-2 text-gray-600 text-xs">{t.definition || ''}</td>
                      <td className="px-2 py-2 text-gray-500 text-xs">
                        {Object.entries(t.translations || {}).map(([lang, val]) => `${lang}: ${val}`).join(', ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>

      {/* Organizations Directory */}
      <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-lg font-semibold text-gray-800">
            Organizations Directory
            <span className="text-sm font-normal text-gray-400 ml-2">({organizations.length} entries)</span>
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={() => downloadJSON({ organizations }, 'organizations.json')}
              className="border border-gray-300 text-gray-600 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors hover:bg-gray-50"
            >
              Download JSON
            </button>
            <label className="bg-uni-blue text-white rounded-lg px-3 py-1.5 text-sm font-medium transition-colors hover:opacity-90 cursor-pointer">
              Upload JSON
              <input
                ref={orgsUploadRef}
                type="file"
                accept=".json"
                onChange={handleOrgsUpload}
                className="hidden"
              />
            </label>
          </div>
        </div>
        <p className="text-xs text-gray-400 mb-3">
          Curated list of unions, federations, and institutions. The AI only references organizations from this list.
          Download the current file, edit it, and upload the updated version.
        </p>

        {organizations.length > 0 && (
          <>
            <button
              onClick={() => setOrgsExpanded(!orgsExpanded)}
              className="text-xs text-uni-blue hover:underline mb-2"
            >
              {orgsExpanded ? 'Hide organizations' : `Show all ${organizations.length} organizations`}
            </button>
            {orgsExpanded && (
              <table className="w-full text-sm mt-2">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left px-2 py-2 font-medium text-gray-600">Name</th>
                    <th className="text-left px-2 py-2 font-medium text-gray-600">Type</th>
                    <th className="text-left px-2 py-2 font-medium text-gray-600">Country</th>
                    <th className="text-left px-2 py-2 font-medium text-gray-600">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {organizations.map((o, i) => (
                    <tr key={i} className="border-b border-gray-100">
                      <td className="px-2 py-2 font-medium text-gray-800">{o.name}</td>
                      <td className="px-2 py-2 text-gray-500 text-xs">{o.type}</td>
                      <td className="px-2 py-2 text-gray-500 text-xs">{o.country}</td>
                      <td className="px-2 py-2 text-gray-600 text-xs">{o.description || ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </div>
  )
}
