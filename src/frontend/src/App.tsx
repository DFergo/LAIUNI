function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-uni-blue text-white px-6 py-4 shadow-md flex items-center justify-between">
        <h1 className="text-xl font-semibold">HRDD Helper</h1>
        <span className="text-sm opacity-75">UNI Global Union</span>
      </header>
      <main className="max-w-4xl mx-auto mt-12 p-6">
        <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 text-center">
          <h2 className="text-2xl font-semibold text-gray-800 mb-2">Hello HRDD</h2>
          <p className="text-gray-500">Scaffolding complete. User flow coming in Sprint 3.</p>
        </div>
      </main>
      <footer className="text-center text-xs text-gray-400 py-3 mt-8">
        This tool provides information, not legal advice. AI responses may contain errors.
      </footer>
    </div>
  )
}

export default App
