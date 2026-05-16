function formatTime(sent_at) {
  if (!sent_at) return ''
  const d = new Date(sent_at)
  return isNaN(d.getTime()) ? '' : d.toLocaleTimeString()
}

export default function MessageLog({ messages = [] }) {
  return (
    <div className="flex flex-col gap-2 max-h-96 overflow-y-auto p-2">
      {messages.map((m) => (
        <div
          key={m.id}
          className={`max-w-xs px-4 py-2 rounded-2xl text-sm ${
            m.direction === 'incoming'
              ? 'self-start bg-gray-100 text-gray-800'
              : 'self-end bg-purple-600 text-white'
          }`}
        >
          {m.content}
          <div className="text-[10px] opacity-60 mt-1">{formatTime(m.sent_at)}</div>
        </div>
      ))}
    </div>
  )
}
