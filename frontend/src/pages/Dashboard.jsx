import { useEffect, useState } from 'react'
import { getAccounts, getBotStatus, addAccount, addAccountBySession, verifyChallenge, deleteAccount } from '../api/client'
import BotStatus from '../components/BotStatus'
import DailyLimit from '../components/DailyLimit'

const EMPTY_FORM = {
  username: '',
  password: '',
  business_name: '',
  service_description: '',
  price_info: '',
  objections_script: '',
  proxy_url: '',
}

export default function Dashboard() {
  const [accounts, setAccounts] = useState([])
  const [statuses, setStatuses] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState(null)
  const [addMode, setAddMode] = useState('password') // 'password' | 'session'
  const [sessionForm, setSessionForm] = useState({ username: '', session_id: '', business_name: '', service_description: '', price_info: '', objections_script: '', proxy_url: '' })
  const [challenge, setChallenge] = useState(null) // { token, hint }
  const [challengeCode, setChallengeCode] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  const loadData = async () => {
    try {
      setError(null)
      const { data: accs } = await getAccounts()
      setAccounts(accs)
      const statusMap = {}
      await Promise.all(
        accs.map(async (a) => {
          try {
            const { data } = await getBotStatus(a.id)
            statusMap[a.id] = data
          } catch {
            statusMap[a.id] = { status: 'error', pause_reason: 'failed to load status' }
          }
        })
      )
      setStatuses(statusMap)
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Failed to load accounts. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleAdd = async (e) => {
    e.preventDefault()
    if (!form.username.trim() || !form.password.trim()) {
      setAddError('Username and password are required.')
      return
    }
    setAdding(true)
    setAddError(null)
    try {
      const { data, status } = await addAccount(form)
      if (data.status === 'challenge_required') {
        setChallenge({ token: data.token, hint: data.hint })
        setShowForm(false)
        return
      }
      setForm(EMPTY_FORM)
      setShowForm(false)
      await loadData()
    } catch (err) {
      setAddError(err.response?.data?.detail ?? 'Failed to connect account.')
    } finally {
      setAdding(false)
    }
  }

  const handleVerify = async (e) => {
    e.preventDefault()
    if (!challengeCode.trim()) return
    setVerifying(true)
    setAddError(null)
    try {
      await verifyChallenge(challenge.token, challengeCode.trim())
      setChallenge(null)
      setChallengeCode('')
      await loadData()
    } catch (err) {
      setAddError(err.response?.data?.detail ?? 'Verification failed. Check the code and try again.')
    } finally {
      setVerifying(false)
    }
  }

  const handleDelete = async (accountId, username) => {
    if (!window.confirm(`Remove @${username}? This will delete all conversations and data.`)) return
    try {
      await deleteAccount(accountId)
      await loadData()
    } catch {
      setError('Failed to delete account.')
    }
  }

  const handleAddBySession = async (e) => {
    e.preventDefault()
    if (!sessionForm.username.trim() || !sessionForm.session_id.trim()) {
      setAddError('Username and Session ID are required.')
      return
    }
    setAdding(true)
    setAddError(null)
    try {
      await addAccountBySession(sessionForm)
      setSessionForm({ username: '', session_id: '', business_name: '', service_description: '', price_info: '', objections_script: '', proxy_url: '' })
      setShowForm(false)
      await loadData()
    } catch (err) {
      setAddError(err.response?.data?.detail ?? 'Failed to connect account via Session ID.')
    } finally {
      setAdding(false)
    }
  }

  const sf = (key) => (e) => setSessionForm(prev => ({ ...prev, [key]: e.target.value }))
  const f = (key) => (e) => setForm(prev => ({ ...prev, [key]: e.target.value }))

  if (loading) return <div className="p-6 text-gray-500">Loading...</div>

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
        <button
          onClick={() => { setShowForm(true); setAddError(null) }}
          className="bg-purple-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-purple-700"
        >
          + Add Instagram Account
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* Instagram challenge verification */}
      {challenge && (
        <div className="bg-amber-50 border-2 border-amber-300 rounded-xl p-6 space-y-4">
          <div className="flex items-start gap-3">
            <span className="text-2xl">🔐</span>
            <div>
              <h2 className="font-semibold text-gray-800 text-lg">Instagram verification required</h2>
              <p className="text-sm text-gray-600 mt-1">
                Instagram sent a verification code to{' '}
                <span className="font-medium">{challenge.hint || 'your email/phone'}</span>.
                Enter it below to complete the connection.
              </p>
            </div>
          </div>

          {addError && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
              {addError}
            </div>
          )}

          <form onSubmit={handleVerify} className="flex gap-3 items-end">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">Verification code</label>
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm tracking-widest text-center text-lg"
                placeholder="123456"
                value={challengeCode}
                onChange={(e) => setChallengeCode(e.target.value)}
                maxLength={8}
                autoFocus
              />
            </div>
            <button
              type="submit"
              disabled={verifying || !challengeCode.trim()}
              className="bg-amber-500 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-amber-600 disabled:opacity-50"
            >
              {verifying ? 'Verifying...' : 'Confirm'}
            </button>
            <button
              type="button"
              onClick={() => { setChallenge(null); setChallengeCode(''); setAddError(null) }}
              className="border px-4 py-2 rounded-lg text-sm hover:bg-gray-50"
            >
              Cancel
            </button>
          </form>
        </div>
      )}

      {/* Add Account Form */}
      {showForm && (
        <div className="bg-white border-2 border-purple-200 rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-800 text-lg">Connect Instagram Account</h2>
            <button onClick={() => { setShowForm(false); setAddError(null) }} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
          </div>

          {/* Mode tabs */}
          <div className="flex gap-2 border-b">
            <button
              type="button"
              onClick={() => { setAddMode('password'); setAddError(null) }}
              className={`pb-2 px-3 text-sm font-medium border-b-2 -mb-px ${addMode === 'password' ? 'border-purple-600 text-purple-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
            >
              Username & Password
            </button>
            <button
              type="button"
              onClick={() => { setAddMode('session'); setAddError(null) }}
              className={`pb-2 px-3 text-sm font-medium border-b-2 -mb-px ${addMode === 'session' ? 'border-purple-600 text-purple-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
            >
              Session ID (bypass IP ban)
            </button>
          </div>

          {addError && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
              {addError}
            </div>
          )}

          {addMode === 'session' && (
            <form onSubmit={handleAddBySession} className="space-y-4">
              <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-800">
                <p className="font-medium mb-1">How to get your Session ID:</p>
                <ol className="list-decimal list-inside space-y-1 text-xs">
                  <li>Open Instagram in Chrome on your phone or any device that's not IP-banned</li>
                  <li>Log in normally</li>
                  <li>Open DevTools → Application → Cookies → instagram.com</li>
                  <li>Find the cookie named <code className="bg-blue-100 px-1 rounded">sessionid</code> and copy its value</li>
                </ol>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Instagram Username</label>
                  <input
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                    placeholder="your_instagram"
                    value={sessionForm.username}
                    onChange={sf('username')}
                    autoComplete="off"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Session ID</label>
                  <input
                    className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
                    placeholder="IGXXXXXXXXXX%3AXXXXXXXXXX%3AXX"
                    value={sessionForm.session_id}
                    onChange={sf('session_id')}
                    autoComplete="off"
                  />
                </div>
              </div>
              <div className="border-t pt-4">
                <p className="text-xs text-gray-500 mb-3 font-medium uppercase tracking-wide">Bot Configuration</p>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Business Name</label>
                    <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="My Company" value={sessionForm.business_name} onChange={sf('business_name')} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Service Description</label>
                    <textarea className="w-full border rounded-lg px-3 py-2 text-sm h-16 resize-none" placeholder="What do you sell?" value={sessionForm.service_description} onChange={sf('service_description')} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Price Info</label>
                    <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="e.g. $299 one-time" value={sessionForm.price_info} onChange={sf('price_info')} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Objections Script</label>
                    <textarea className="w-full border rounded-lg px-3 py-2 text-sm h-16 resize-none" placeholder="How to handle objections" value={sessionForm.objections_script} onChange={sf('objections_script')} />
                  </div>
                </div>
              </div>
              <div className="border-t pt-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Proxy URL <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <input className="w-full border rounded-lg px-3 py-2 text-sm font-mono" placeholder="http://username:password@host:port" value={sessionForm.proxy_url} onChange={sf('proxy_url')} autoComplete="off" />
              </div>
              {addError && (
                <div className="bg-red-50 border border-red-300 text-red-700 rounded-lg px-4 py-3 text-sm font-medium">
                  {addError}
                </div>
              )}
              <div className="flex gap-3 pt-2">
                <button type="submit" disabled={adding} className="bg-purple-600 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50">
                  {adding ? 'Connecting...' : 'Connect via Session ID'}
                </button>
                <button type="button" onClick={() => setShowForm(false)} className="border px-4 py-2 rounded-lg text-sm hover:bg-gray-50">Cancel</button>
              </div>
            </form>
          )}

          {addMode === 'password' && <form onSubmit={handleAdd} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Instagram Username</label>
                <input
                  className="w-full border rounded-lg px-3 py-2 text-sm"
                  placeholder="your_instagram"
                  value={form.username}
                  onChange={f('username')}
                  autoComplete="off"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Instagram Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    className="w-full border rounded-lg px-3 py-2 text-sm pr-10"
                    placeholder="••••••••"
                    value={form.password}
                    onChange={f('password')}
                    autoComplete="off"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(v => !v)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    tabIndex={-1}
                  >
                    {showPassword ? '🙈' : '👁️'}
                  </button>
                </div>
              </div>
            </div>

            <div className="border-t pt-4">
              <p className="text-xs text-gray-500 mb-3 font-medium uppercase tracking-wide">Bot Configuration</p>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Business Name</label>
                  <input
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                    placeholder="My Company"
                    value={form.business_name}
                    onChange={f('business_name')}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Service Description</label>
                  <textarea
                    className="w-full border rounded-lg px-3 py-2 text-sm h-16 resize-none"
                    placeholder="What do you sell? e.g. online marketing courses"
                    value={form.service_description}
                    onChange={f('service_description')}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Price Info</label>
                  <input
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                    placeholder="e.g. $299 one-time, or from $49/month"
                    value={form.price_info}
                    onChange={f('price_info')}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Objections Script</label>
                  <textarea
                    className="w-full border rounded-lg px-3 py-2 text-sm h-16 resize-none"
                    placeholder="e.g. If they say 'expensive' — explain the ROI and offer a payment plan"
                    value={form.objections_script}
                    onChange={f('objections_script')}
                  />
                </div>
              </div>
            </div>

            <div className="border-t pt-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Proxy URL <span className="text-gray-400 font-normal">(recommended)</span>
              </label>
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
                placeholder="http://username:password@host:port"
                value={form.proxy_url}
                onChange={f('proxy_url')}
                autoComplete="off"
              />
              <p className="text-xs text-gray-400 mt-1">
                Residential proxy з тієї ж країни що й акаунт — захищає від банів. Webshare, Smartproxy, IPRoyal.
              </p>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                type="submit"
                disabled={adding}
                className="bg-purple-600 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50"
              >
                {adding ? 'Connecting... (may take 30s)' : 'Connect Account'}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="border px-4 py-2 rounded-lg text-sm hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </form>}
        </div>
      )}

      {/* Empty state */}
      {!showForm && accounts.length === 0 && (
        <div className="bg-gray-50 rounded-xl p-12 text-center">
          <p className="text-4xl mb-4">🤖</p>
          <p className="text-gray-700 font-semibold text-lg mb-2">No accounts connected yet</p>
          <p className="text-gray-400 text-sm mb-6">Click "Add Instagram Account" to get started</p>
          <button
            onClick={() => setShowForm(true)}
            className="bg-purple-600 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-purple-700"
          >
            + Add Instagram Account
          </button>
        </div>
      )}

      {/* Account cards */}
      {accounts.map((account) => {
        const st = statuses[account.id] || {}
        return (
          <div key={account.id} className="bg-white border rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-800">@{account.username}</h2>
                <p className="text-xs text-gray-400">
                  Added {new Date(account.created_at).toLocaleDateString()}
                </p>
              </div>
              <button
                onClick={() => handleDelete(account.id, account.username)}
                className="text-xs text-red-400 hover:text-red-600 border border-red-200 px-3 py-1 rounded-lg"
              >
                Remove
              </button>
            </div>
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
