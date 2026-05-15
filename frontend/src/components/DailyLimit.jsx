export default function DailyLimit({ sent, limit }) {
  const pct = limit > 0 ? Math.round((sent / limit) * 100) : 0
  const color = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-yellow-500' : 'bg-green-500'
  return (
    <div className="bg-white rounded-xl border p-5">
      <p className="text-xs uppercase font-semibold text-gray-500 tracking-widest">Daily Messages</p>
      <p className="text-2xl font-bold mt-1">
        {sent} <span className="text-gray-400 text-lg font-normal">/ {limit}</span>
      </p>
      <div className="mt-3 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-gray-400 mt-1">{pct}% used today</p>
    </div>
  )
}
