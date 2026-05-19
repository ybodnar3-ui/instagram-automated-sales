import { useState, useEffect } from 'react'

const STORAGE_KEY = 'dashboard_api_key'
const REQUIRED_KEY = import.meta.env.VITE_API_KEY || ''

export function getStoredKey() {
  return localStorage.getItem(STORAGE_KEY) || ''
}

export default function AuthGate({ children }) {
  const [unlocked, setUnlocked] = useState(false)
  const [input, setInput] = useState('')
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!REQUIRED_KEY) { setUnlocked(true); return }
    if (getStoredKey() === REQUIRED_KEY) setUnlocked(true)
  }, [])

  if (!REQUIRED_KEY || unlocked) return children

  const handleSubmit = (e) => {
    e.preventDefault()
    if (input.trim() === REQUIRED_KEY) {
      localStorage.setItem(STORAGE_KEY, input.trim())
      setUnlocked(true)
    } else {
      setError(true)
      setInput('')
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-lg p-8 w-full max-w-sm space-y-6">
        <div className="text-center">
          <p className="text-3xl mb-2">🤖</p>
          <h1 className="text-xl font-bold text-gray-800">Instagram Sales Bot</h1>
          <p className="text-sm text-gray-400 mt-1">Enter access key to continue</p>
        </div>
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-2 text-sm text-center">
            Wrong key. Try again.
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="password"
            autoFocus
            className="w-full border rounded-lg px-4 py-3 text-sm tracking-widest text-center"
            placeholder="••••••••••••"
            value={input}
            onChange={(e) => { setInput(e.target.value); setError(false) }}
          />
          <button
            type="submit"
            className="w-full bg-purple-600 text-white py-3 rounded-lg text-sm font-medium hover:bg-purple-700"
          >
            Unlock
          </button>
        </form>
      </div>
    </div>
  )
}
