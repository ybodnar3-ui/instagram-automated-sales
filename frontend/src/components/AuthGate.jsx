import { useState, useEffect } from 'react'
import axios from 'axios'

const STORAGE_KEY = 'dashboard_api_key'
const BASE_URL = import.meta.env.VITE_API_URL || ''

export function getStoredKey() {
  return localStorage.getItem(STORAGE_KEY) || ''
}

async function verifyKey(key) {
  // Verify the key against the backend — avoids baking any secret into the JS bundle.
  try {
    await axios.get(`${BASE_URL}/accounts`, {
      headers: key ? { 'X-API-Key': key } : {},
    })
    return true
  } catch (err) {
    if (err.response?.status === 401) return false
    // Network errors or server errors: unlock so the user sees the real error in the dashboard
    return true
  }
}

export default function AuthGate({ children }) {
  const [unlocked, setUnlocked] = useState(false)
  const [input, setInput] = useState('')
  const [error, setError] = useState(false)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    const stored = getStoredKey()
    // Auto-unlock with stored key (verified against backend)
    verifyKey(stored).then((ok) => {
      if (ok) setUnlocked(true)
    })
  }, [])

  if (unlocked) return children

  const handleSubmit = async (e) => {
    e.preventDefault()
    const key = input.trim()
    setChecking(true)
    const ok = await verifyKey(key)
    setChecking(false)
    if (ok) {
      localStorage.setItem(STORAGE_KEY, key)
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
            disabled={checking}
            className="w-full bg-purple-600 text-white py-3 rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50"
          >
            {checking ? 'Checking...' : 'Unlock'}
          </button>
        </form>
      </div>
    </div>
  )
}
