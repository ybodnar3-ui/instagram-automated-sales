import { useEffect, useState } from 'react'
import { getAccounts, getDailyStats, getSummary } from '../api/client'
import ConversionChart from '../components/ConversionChart'

export default function Stats() {
  const [accounts, setAccounts] = useState([])
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [days, setDays] = useState(7)
  const [chartData, setChartData] = useState([])
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)

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
    Promise.all([
      getDailyStats(selectedAccount, days),
      getSummary(selectedAccount),
    ])
      .then(([{ data: chart }, { data: sum }]) => {
        setChartData(chart)
        setSummary(sum)
      })
      .catch(() => setError('Failed to load stats. Please try again.'))
  }, [selectedAccount, days])

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold text-gray-800">Stats</h1>
        <select
          className="text-sm border rounded px-2 py-1"
          value={selectedAccount || ''}
          onChange={(e) => setSelectedAccount(Number(e.target.value))}
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>@{a.username}</option>
          ))}
        </select>
        <select
          className="text-sm border rounded px-2 py-1"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
        </select>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Messages Sent', value: summary.total_messages_sent },
            { label: 'Conversations', value: summary.total_conversations },
            { label: 'Conversions', value: summary.total_conversions },
            { label: 'Conversion Rate', value: `${summary.conversion_rate_pct}%` },
          ].map(({ label, value }) => (
            <div key={label} className="bg-white rounded-xl border p-4">
              <p className="text-xs uppercase text-gray-400 font-semibold">{label}</p>
              <p className="text-2xl font-bold text-gray-800 mt-1">{value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="bg-white rounded-xl border p-5">
        <h2 className="text-sm font-semibold text-gray-600 mb-4">Messages Over Time</h2>
        <ConversionChart data={chartData} />
      </div>

      {summary && (
        <div className="bg-white rounded-xl border p-5">
          <h2 className="text-sm font-semibold text-gray-600 mb-2">Token Usage</h2>
          <p className="text-3xl font-bold text-purple-600">
            {summary.total_tokens_used.toLocaleString()}
          </p>
          <p className="text-xs text-gray-400 mt-1">total tokens consumed</p>
        </div>
      )}
    </div>
  )
}
