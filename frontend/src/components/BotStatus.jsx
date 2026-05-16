import { useState } from 'react'
import { pauseBot, resumeBot } from '../api/client'

const STATUS_STYLES = {
  active: 'bg-green-100 text-green-800 border-green-300',
  paused: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  error: 'bg-red-100 text-red-800 border-red-300',
}

export default function BotStatus({ accountId, status, pauseReason, onStatusChange }) {
  const [loading, setLoading] = useState(false)
  const [actionError, setActionError] = useState(null)

  const handleToggle = async () => {
    const confirmed = window.confirm(
      status === 'active' ? 'Pause the bot?' : 'Resume the bot?'
    )
    if (!confirmed) return
    setLoading(true)
    setActionError(null)
    try {
      if (status === 'active') {
        await pauseBot(accountId)
      } else {
        await resumeBot(accountId)
      }
      onStatusChange()
    } catch (err) {
      setActionError(err.response?.data?.detail ?? 'Action failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={`rounded-xl border-2 p-6 ${STATUS_STYLES[status] || STATUS_STYLES.error}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase font-semibold tracking-widest opacity-70">Bot Status</p>
          <p className="text-3xl font-bold mt-1">{status?.toUpperCase() ?? '—'}</p>
          {pauseReason && (
            <p className="text-sm mt-1 opacity-70">Reason: {pauseReason}</p>
          )}
          {actionError && (
            <p className="text-sm mt-2 text-red-600 font-medium">{actionError}</p>
          )}
        </div>
        {status !== 'error' && (
          <button
            onClick={handleToggle}
            disabled={loading}
            className="px-5 py-2 rounded-lg bg-gray-800 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-50"
          >
            {loading ? '...' : status === 'active' ? 'Pause' : 'Resume'}
          </button>
        )}
      </div>
    </div>
  )
}
