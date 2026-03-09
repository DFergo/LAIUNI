import { useState } from 'react'
import FrontendsTab from './FrontendsTab'

interface Props {
  onLogout: () => void
}

const TABS = ['Frontends', 'Prompts', 'LLM', 'RAG', 'Sessions', 'SMTP'] as const
type Tab = typeof TABS[number]

export default function Dashboard({ onLogout }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('Frontends')

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-uni-dark text-white shadow-md">
        <div className="px-6 py-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold">HRDD Helper — Admin Panel</h1>
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
                  ? 'border-uni-blue text-white'
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
        {activeTab !== 'Frontends' && (
          <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
            <p className="text-gray-400">{activeTab} tab coming in Sprint 6.</p>
          </div>
        )}
      </main>
    </div>
  )
}
