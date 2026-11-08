import { useState } from 'react'
import FrontendsTab from './FrontendsTab'
import PromptsTab from './PromptsTab'
import LLMTab from './LLMTab'
import RAGTab from './RAGTab'
import SessionsTab from './SessionsTab'
import SMTPTab from './SMTPTab'
import RegisteredUsersTab from './RegisteredUsersTab'
import BrandingTab from './BrandingTab'
import { brand, loadBrand } from './brand'

interface Props {
  onLogout: () => void
}

const TABS = ['Frontends', 'Prompts', 'LLM', 'RAG', 'Sessions', 'SMTP', 'Registered Users', 'Branding'] as const
type Tab = typeof TABS[number]

export default function Dashboard({ onLogout }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('Frontends')
  const [, repaint] = useState(0)   // the tokens live outside React: bump to re-read them

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-brand-dark text-white shadow-md">
        <div className="px-6 py-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold">{brand().tool_name} — Admin Panel</h1>
          <button
            onClick={onLogout}
            className="text-sm bg-white/10 hover:bg-white/20 rounded-lg px-3 py-1.5 transition-colors"
          >
            Logout
          </button>
        </div>
        <nav className="px-6 flex gap-1">
          {TABS.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                activeTab === tab
                  ? 'border-brand-primary text-white'
                  : 'border-transparent text-white/60 hover:text-white/80'
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </header>

      <main className="max-w-6xl mx-auto mt-6 p-6">
        {activeTab === 'Frontends' && <FrontendsTab />}
        {activeTab === 'Prompts' && <PromptsTab />}
        {activeTab === 'LLM' && <LLMTab />}
        {activeTab === 'RAG' && <RAGTab />}
        {activeTab === 'Sessions' && <SessionsTab />}
        {activeTab === 'SMTP' && <SMTPTab />}
        {activeTab === 'Registered Users' && <RegisteredUsersTab />}
        {activeTab === 'Branding' && <BrandingTab onChanged={() => loadBrand().then(() => repaint(n => n + 1))} />}
      </main>
    </div>
  )
}
