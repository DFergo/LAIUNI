interface Props {
  onLogout: () => void
}

export default function Dashboard({ onLogout }: Props) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-uni-dark text-white px-6 py-4 shadow-md flex items-center justify-between">
        <h1 className="text-xl font-semibold">HRDD Helper — Admin Panel</h1>
        <button
          onClick={onLogout}
          className="text-sm bg-white/10 hover:bg-white/20 rounded-lg px-3 py-1.5 transition-colors"
        >
          Logout
        </button>
      </header>

      <main className="max-w-6xl mx-auto mt-8 p-6">
        <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
          <h2 className="text-2xl font-semibold text-gray-800 mb-2">Welcome</h2>
          <p className="text-gray-500">Admin panel tabs coming in Sprint 6.</p>
        </div>
      </main>
    </div>
  )
}
