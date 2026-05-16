import { useEffect, useState } from 'react'
import { getAccounts, getOutboundTargets, addOutboundTarget, deleteOutboundTarget } from '../api/client'

const STATUS_COLORS = {
  pending: 'bg-yellow-50 text-yellow-700',
  sent: 'bg-green-50 text-green-700',
  failed: 'bg-red-50 text-red-700',
  skipped: 'bg-gray-100 text-gray-500',
}

export default function Outbound() {
  const [accounts, setAccounts] = useState([])
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [targets, setTargets] = useState([])
  const [username, setUsername] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState(null)
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    getAccounts()
      .then(({ data }) => {
        setAccounts(data)
        if (data.length > 0) setSelectedAccount(data[0].id)
      })
      .catch(() => setError('Failed to load accounts.'))
  }, [])

  useEffect(() => {
    if (!selectedAccount) return
    setError(null)
    getOutboundTargets(selectedAccount)
      .then(({ data }) => setTargets(data))
      .catch(() => setError('Failed to load outbound targets.'))
  }, [selectedAccount])

  const reload = () => {
    if (!selectedAccount) return
    getOutboundTargets(selectedAccount).then(({ data }) => setTargets(data)).catch(() => {})
  }

  const handleAdd = async () => {
    const u = username.trim().replace(/^@/, '')
    if (!u) { setError('Username is required.'); return }
    setAdding(true)
    setError(null)
    try {
      await addOutboundTarget(selectedAccount, { instagram_username: u, initial_message: message.trim() || null })
      setUsername('')
      setMessage('')
      reload()
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Failed to add target.')
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteOutboundTarget(selectedAccount, id)
      reload()
    } catch {
      setError('Delete failed.')
    }
  }

  const counts = targets.reduce((acc, t) => { acc[t.status] = (acc[t.status] || 0) + 1; return acc }, {})

  return (
    <div className="p-6 max-w-3xl space-y-6">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold text-gray-800">Outbound</h1>
        <select
          className="text-sm border rounded px-2 py-1"
          value={selectedAccount || ''}
          onChange={(e) => setSelectedAccount(Number(e.target.value))}
        >
          {accounts.map((a) => <option key={a.id} value={a.id}>@{a.username}</option>)}
        </select>
      </div>

      <p className="text-sm text-gray-500">
        Add Instagram usernames for the bot to message proactively. The bot sends max 5 DMs/day (configurable in Settings).
        Leave message empty to use the default from Settings.
      </p>

      <div className="grid grid-cols-4 gap-3">
        {['pending', 'sent', 'failed', 'skipped'].map((s) => (
          <div key={s} className="bg-white border rounded-xl p-3 text-center">
            <div className="text-2xl font-bold text-gray-800">{counts[s] || 0}</div>
            <div className="text-xs text-gray-500 capitalize">{s}</div>
          </div>
        ))}
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">{error}</div>}

      <div className="bg-white border rounded-xl p-5 space-y-3">
        <h2 className="font-semibold text-gray-700">Add Target</h2>
        <div className="flex gap-3">
          <input
            className="flex-1 border rounded-lg px-3 py-2 text-sm"
            placeholder="@instagram_username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          />
          <button
            onClick={handleAdd}
            disabled={adding}
            className="bg-purple-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-purple-700 disabled:opacity-50"
          >
            {adding ? 'Adding...' : 'Add'}
          </button>
        </div>
        <textarea
          className="w-full border rounded-lg px-3 py-2 text-sm h-16 resize-none"
          placeholder="Custom first message (optional — leave empty to use default from Settings)"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
      </div>

      <div className="space-y-2">
        {targets.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-6">No targets yet.</p>
        )}
        {targets.map((t) => (
          <div key={t.id} className="bg-white border rounded-xl p-4 flex items-center justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm">@{t.instagram_username}</span>
                <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[t.status] || 'bg-gray-100'}`}>
                  {t.status}
                </span>
              </div>
              {t.initial_message && (
                <p className="text-xs text-gray-400 truncate mt-1">{t.initial_message}</p>
              )}
              {t.error_message && (
                <p className="text-xs text-red-500 truncate mt-1">{t.error_message}</p>
              )}
              {t.sent_at && (
                <p className="text-xs text-gray-400 mt-1">Sent: {new Date(t.sent_at).toLocaleString()}</p>
              )}
            </div>
            {t.status === 'pending' && (
              <button
                onClick={() => handleDelete(t.id)}
                className="text-xs px-2 py-1 bg-red-50 text-red-600 border border-red-200 rounded hover:bg-red-100 shrink-0"
              >
                Remove
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
