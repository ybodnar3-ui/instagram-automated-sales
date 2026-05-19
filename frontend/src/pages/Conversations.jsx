import { useEffect, useState } from 'react'
import { getAccounts, getConversations, getConversation, takeoverConversation, restoreBot } from '../api/client'
import MessageLog from '../components/MessageLog'

const STAGES = ['all', 'new', 'in_progress', 'converted', 'dead']

export default function Conversations() {
  const [accounts, setAccounts] = useState([])
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [stage, setStage] = useState('all')
  const [conversations, setConversations] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [listError, setListError] = useState(null)
  const [detailError, setDetailError] = useState(null)
  const [actionError, setActionError] = useState(null)

  useEffect(() => {
    getAccounts()
      .then(({ data }) => {
        setAccounts(data)
        if (data.length > 0) setSelectedAccount(data[0].id)
      })
      .catch(() => setListError('Failed to load accounts.'))
  }, [])

  useEffect(() => {
    if (!selectedAccount) return
    setListError(null)
    getConversations(selectedAccount, stage === 'all' ? null : stage)
      .then(({ data }) => setConversations(data))
      .catch(() => setListError('Failed to load conversations.'))
  }, [selectedAccount, stage])

  const openConversation = async (threadId) => {
    setSelected(threadId)
    setDetail(null)
    setDetailError(null)
    try {
      const { data } = await getConversation(selectedAccount, threadId)
      setDetail(data)
    } catch {
      setDetailError('Failed to load conversation.')
    }
  }

  const reloadConversations = () => {
    if (!selectedAccount) return
    getConversations(selectedAccount, stage === 'all' ? null : stage)
      .then(({ data }) => setConversations(data))
      .catch(() => {})
  }

  const handleTakeover = async (threadId) => {
    setActionError(null)
    try {
      await takeoverConversation(selectedAccount, threadId)
      await openConversation(threadId)
      reloadConversations()
    } catch {
      setActionError('Failed to take over conversation.')
    }
  }

  const handleRestoreBot = async (threadId) => {
    setActionError(null)
    try {
      await restoreBot(selectedAccount, threadId)
      await openConversation(threadId)
      reloadConversations()
    } catch {
      setActionError('Failed to restore bot.')
    }
  }

  return (
    <div className="flex h-[calc(100vh-52px)]">
      <div className="w-72 border-r flex flex-col">
        <div className="p-3 border-b">
          <select
            className="w-full text-sm border rounded px-2 py-1"
            value={selectedAccount || ''}
            onChange={(e) => setSelectedAccount(Number(e.target.value))}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>@{a.username}</option>
            ))}
          </select>
          <div className="flex gap-1 mt-2 flex-wrap">
            {STAGES.map((s) => (
              <button
                key={s}
                onClick={() => setStage(s)}
                className={`text-xs px-2 py-0.5 rounded-full ${
                  stage === s ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-600'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {listError && (
          <div className="p-3 text-xs text-red-600 bg-red-50">{listError}</div>
        )}

        <div className="overflow-y-auto flex-1">
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => openConversation(c.thread_id)}
              className={`w-full text-left p-3 border-b hover:bg-gray-50 ${
                selected === c.thread_id ? 'bg-purple-50' : ''
              }`}
            >
              <div className="font-medium text-sm text-gray-800">@{c.username}</div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs text-gray-400">{c.stage}</span>
                {!c.bot_active && (
                  <span className="text-xs bg-yellow-100 text-yellow-700 px-1 rounded">human</span>
                )}
              </div>
              <div className="text-xs text-gray-400">{c.messages_count} messages</div>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col">
        {actionError && (
          <div className="px-4 py-2 bg-red-50 border-b border-red-200 text-sm text-red-600">
            {actionError}
          </div>
        )}
        {detail ? (
          <>
            <div className="p-3 border-b flex items-center justify-between">
              <span className="font-semibold text-gray-700">@{detail.conversation.username}</span>
              <div className="flex gap-2">
                {detail.conversation.bot_active ? (
                  <button
                    onClick={() => handleTakeover(detail.conversation.thread_id)}
                    className="text-xs bg-yellow-100 text-yellow-800 px-3 py-1 rounded-lg hover:bg-yellow-200"
                  >
                    Take Over
                  </button>
                ) : (
                  <button
                    onClick={() => handleRestoreBot(detail.conversation.thread_id)}
                    className="text-xs bg-green-100 text-green-800 px-3 py-1 rounded-lg hover:bg-green-200"
                  >
                    Restore Bot
                  </button>
                )}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <MessageLog messages={detail.messages} />
            </div>
          </>
        ) : detailError ? (
          <div className="flex-1 flex items-center justify-center text-red-500 text-sm">
            {detailError}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            {selected ? 'Loading...' : 'Select a conversation'}
          </div>
        )}
      </div>
    </div>
  )
}
