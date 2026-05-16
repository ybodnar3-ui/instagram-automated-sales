import { useEffect, useState } from 'react'
import { getAccounts, getTriggers, createTrigger, updateTrigger, deleteTrigger } from '../api/client'

const EMPTY_FORM = { keyword: '', response_template: '', use_ai_followup: false, is_active: true }

export default function Triggers() {
  const [accounts, setAccounts] = useState([])
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [triggers, setTriggers] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [editingId, setEditingId] = useState(null)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

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
    getTriggers(selectedAccount)
      .then(({ data }) => setTriggers(data))
      .catch(() => setError('Failed to load triggers.'))
  }, [selectedAccount])

  const reload = () => {
    if (!selectedAccount) return
    getTriggers(selectedAccount).then(({ data }) => setTriggers(data)).catch(() => {})
  }

  const handleSave = async () => {
    if (!form.keyword.trim() || !form.response_template.trim()) {
      setError('Keyword and response template are required.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (editingId) {
        await updateTrigger(selectedAccount, editingId, form)
      } else {
        await createTrigger(selectedAccount, form)
      }
      setForm(EMPTY_FORM)
      setEditingId(null)
      reload()
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  const handleEdit = (t) => {
    setEditingId(t.id)
    setForm({ keyword: t.keyword, response_template: t.response_template, use_ai_followup: t.use_ai_followup, is_active: t.is_active })
  }

  const handleDelete = async (id) => {
    try {
      await deleteTrigger(selectedAccount, id)
      reload()
    } catch {
      setError('Delete failed.')
    }
  }

  const handleToggle = async (t) => {
    try {
      await updateTrigger(selectedAccount, t.id, { is_active: !t.is_active })
      reload()
    } catch {
      setError('Toggle failed.')
    }
  }

  return (
    <div className="p-6 max-w-3xl space-y-6">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold text-gray-800">Triggers</h1>
        <select
          className="text-sm border rounded px-2 py-1"
          value={selectedAccount || ''}
          onChange={(e) => setSelectedAccount(Number(e.target.value))}
        >
          {accounts.map((a) => <option key={a.id} value={a.id}>@{a.username}</option>)}
        </select>
      </div>

      <p className="text-sm text-gray-500">
        When an incoming message contains the keyword, the bot sends the template response instantly.
        Use <code className="bg-gray-100 px-1 rounded">{'{username}'}</code> or <code className="bg-gray-100 px-1 rounded">{'{full_name}'}</code> for personalization.
      </p>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">{error}</div>}

      <div className="bg-white border rounded-xl p-5 space-y-4">
        <h2 className="font-semibold text-gray-700">{editingId ? 'Edit Trigger' : 'Add Trigger'}</h2>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Keyword</label>
          <input
            className="w-full border rounded-lg px-3 py-2 text-sm"
            placeholder="e.g. + or price or info"
            value={form.keyword}
            onChange={(e) => setForm(f => ({ ...f, keyword: e.target.value }))}
          />
          <p className="text-xs text-gray-400 mt-1">Case-insensitive. Matches if the keyword appears anywhere in the message.</p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Response Template</label>
          <textarea
            className="w-full border rounded-lg px-3 py-2 text-sm h-24 resize-none"
            placeholder="Hi {username}! Thanks for your interest. Here's what we offer..."
            value={form.response_template}
            onChange={(e) => setForm(f => ({ ...f, response_template: e.target.value }))}
          />
        </div>
        <div className="flex items-center gap-6">
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              checked={form.use_ai_followup}
              onChange={(e) => setForm(f => ({ ...f, use_ai_followup: e.target.checked }))}
            />
            Also send AI follow-up after template
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm(f => ({ ...f, is_active: e.target.checked }))}
            />
            Active
          </label>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-purple-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-purple-700 disabled:opacity-50"
          >
            {saving ? 'Saving...' : editingId ? 'Update' : 'Add Trigger'}
          </button>
          {editingId && (
            <button
              onClick={() => { setEditingId(null); setForm(EMPTY_FORM) }}
              className="text-sm px-4 py-2 rounded-lg border hover:bg-gray-50"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      <div className="space-y-2">
        {triggers.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-6">No triggers yet. Add one above.</p>
        )}
        {triggers.map((t) => (
          <div key={t.id} className={`bg-white border rounded-xl p-4 flex items-start justify-between gap-4 ${!t.is_active ? 'opacity-50' : ''}`}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-sm bg-purple-50 text-purple-700 px-2 py-0.5 rounded">{t.keyword}</span>
                {t.use_ai_followup && <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded">+AI</span>}
                {!t.is_active && <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded">inactive</span>}
              </div>
              <p className="text-sm text-gray-600 truncate">{t.response_template}</p>
            </div>
            <div className="flex gap-2 shrink-0">
              <button onClick={() => handleToggle(t)} className="text-xs px-2 py-1 border rounded hover:bg-gray-50">
                {t.is_active ? 'Disable' : 'Enable'}
              </button>
              <button onClick={() => handleEdit(t)} className="text-xs px-2 py-1 border rounded hover:bg-gray-50">Edit</button>
              <button onClick={() => handleDelete(t.id)} className="text-xs px-2 py-1 bg-red-50 text-red-600 border border-red-200 rounded hover:bg-red-100">Del</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
