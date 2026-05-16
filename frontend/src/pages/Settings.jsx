import { useEffect, useState } from 'react'
import { getAccounts, getBotConfig, updateConfig } from '../api/client'

const MODELS = [
  { value: 'claude-haiku-3-5-20251001', label: 'Haiku 3.5 (fast, cheap)' },
  { value: 'claude-sonnet-4-6', label: 'Sonnet 4.6 (smart, slower)' },
]

export default function Settings() {
  const [accounts, setAccounts] = useState([])
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [config, setConfig] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveState, setSaveState] = useState(null) // null | 'saved' | 'error'
  const [saveError, setSaveError] = useState(null)
  const [loadError, setLoadError] = useState(null)

  useEffect(() => {
    getAccounts()
      .then(({ data }) => {
        setAccounts(data)
        if (data.length > 0) setSelectedAccount(data[0].id)
      })
      .catch(() => setLoadError('Failed to load accounts.'))
  }, [])

  useEffect(() => {
    if (!selectedAccount) return
    setLoadError(null)
    setConfig(null)
    getBotConfig(selectedAccount)
      .then(({ data }) => setConfig(data))
      .catch(() => setLoadError('Failed to load bot config.'))
  }, [selectedAccount])

  const handleSave = async () => {
    setSaving(true)
    setSaveState(null)
    setSaveError(null)
    try {
      await updateConfig(selectedAccount, config)
      setSaveState('saved')
      setTimeout(() => setSaveState(null), 2000)
    } catch (err) {
      setSaveState('error')
      setSaveError(err.response?.data?.detail ?? 'Failed to save. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const updateField = (key, value) => setConfig(prev => ({ ...prev, [key]: value }))

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold text-gray-800">Settings</h1>
        <select
          className="text-sm border rounded px-2 py-1"
          value={selectedAccount || ''}
          onChange={(e) => setSelectedAccount(Number(e.target.value))}
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>@{a.username}</option>
          ))}
        </select>
      </div>

      {loadError && (
        <div className="bg-red-50 border border-red-300 text-red-700 rounded-lg px-4 py-3 text-sm">
          {loadError}
        </div>
      )}

      {config && (
        <div className="bg-white rounded-xl border p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Business Name</label>
            <input
              type="text"
              className="w-full border rounded-lg px-3 py-2 text-sm"
              value={config.business_name || ''}
              onChange={(e) => updateField('business_name', e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Service Description</label>
            <textarea
              className="w-full border rounded-lg px-3 py-2 text-sm h-24 resize-none"
              value={config.service_description || ''}
              onChange={(e) => updateField('service_description', e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Price Info</label>
            <input
              type="text"
              className="w-full border rounded-lg px-3 py-2 text-sm"
              value={config.price_info || ''}
              onChange={(e) => updateField('price_info', e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Objections Script</label>
            <textarea
              className="w-full border rounded-lg px-3 py-2 text-sm h-24 resize-none"
              value={config.objections_script || ''}
              onChange={(e) => updateField('objections_script', e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">LLM Model</label>
            <select
              className="w-full border rounded-lg px-3 py-2 text-sm"
              value={config.llm_model || ''}
              onChange={(e) => updateField('llm_model', e.target.value)}
            >
              {MODELS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Daily Limit</label>
              <input
                type="number"
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={config.max_messages_per_day || 80}
                onChange={(e) => updateField('max_messages_per_day', Number(e.target.value))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Min Delay (s)</label>
              <input
                type="number"
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={config.min_delay_sec || 8}
                onChange={(e) => updateField('min_delay_sec', Number(e.target.value))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Max Delay (s)</label>
              <input
                type="number"
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={config.max_delay_sec || 25}
                onChange={(e) => updateField('max_delay_sec', Number(e.target.value))}
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="warmup"
              className="h-4 w-4"
              checked={config.warmup_mode || false}
              onChange={(e) => updateField('warmup_mode', e.target.checked)}
            />
            <label htmlFor="warmup" className="text-sm text-gray-700">
              Enable Warmup Mode (auto-limit by account age)
            </label>
          </div>

          {saveState === 'error' && saveError && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {saveError}
            </div>
          )}

          <button
            onClick={handleSave}
            disabled={saving}
            className={`w-full py-2 rounded-lg font-medium text-white disabled:opacity-50 ${
              saveState === 'error'
                ? 'bg-red-500 hover:bg-red-600'
                : 'bg-purple-600 hover:bg-purple-700'
            }`}
          >
            {saving ? 'Saving...' : saveState === 'saved' ? 'Saved!' : saveState === 'error' ? 'Save Failed' : 'Save Settings'}
          </button>
        </div>
      )}
    </div>
  )
}
