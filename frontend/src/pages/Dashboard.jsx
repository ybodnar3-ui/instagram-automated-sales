import { useEffect, useState } from 'react'
import { getAccounts, getBotStatus } from '../api/client'
import BotStatus from '../components/BotStatus'
import DailyLimit from '../components/DailyLimit'

export default function Dashboard() {
  const [accounts, setAccounts] = useState([])
  const [statuses, setStatuses] = useState({})
  const [loading, setLoading] = useState(true)

  const loadData = async () => {
    try {
      const { data: accs } = await getAccounts()
      setAccounts(accs)
      const statusMap = {}
      await Promise.all(
        accs.map(async (a) => {
          const { data } = await getBotStatus(a.id)
          statusMap[a.id] = data
        })
      )
      setStatuses(statusMap)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 30000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return <div className="p-6 text-gray-500">Loading...</div>

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
      {accounts.length === 0 && (
        <div className="bg-gray-50 rounded-xl p-8 text-center text-gray-400">
          No accounts configured. Add an Instagram account to get started.
        </div>
      )}
      {accounts.map((account) => {
        const st = statuses[account.id] || {}
        return (
          <div key={account.id} className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-700">@{account.username}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <BotStatus
                accountId={account.id}
                status={st.status}
                pauseReason={st.pause_reason}
                onStatusChange={loadData}
              />
              <DailyLimit sent={st.messages_today || 0} limit={st.daily_limit || 80} />
            </div>
          </div>
        )
      })}
    </div>
  )
}
