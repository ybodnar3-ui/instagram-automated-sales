import axios from 'axios'

const STORAGE_KEY = 'dashboard_api_key'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const key = localStorage.getItem(STORAGE_KEY) || import.meta.env.VITE_API_KEY || ''
  if (key) config.headers['X-API-Key'] = key
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status
    const detail = err.response?.data?.detail ?? err.message
    console.error(`[API] ${err.config?.method?.toUpperCase()} ${err.config?.url} → ${status ?? 'network error'}: ${detail}`)
    return Promise.reject(err)
  }
)

export const getAccounts = () => api.get('/accounts')
export const addAccount = (data) => api.post('/accounts', data)
export const addAccountBySession = (data) => api.post('/accounts/session-login', data)
export const verifyChallenge = (token, code) => api.post('/accounts/challenge/verify', { token, code })
export const deleteAccount = (accountId) => api.delete(`/accounts/${accountId}`)
export const getBotStatus = (accountId) => api.get(`/bot/${accountId}/status`)
export const getBotConfig = (accountId) => api.get(`/bot/${accountId}/config`)
export const pauseBot = (accountId) => api.post(`/bot/${accountId}/pause`)
export const resumeBot = (accountId) => api.post(`/bot/${accountId}/resume`)
export const updateConfig = (accountId, data) => api.put(`/bot/${accountId}/config`, data)
export const getConversations = (accountId, stage) =>
  api.get(`/conversations/${accountId}`, { params: stage ? { stage } : {} })
export const getConversation = (accountId, threadId) =>
  api.get(`/conversations/${accountId}/${threadId}`)
export const takeoverConversation = (accountId, threadId) =>
  api.post(`/conversations/${accountId}/${threadId}/takeover`)
export const restoreBot = (accountId, threadId) =>
  api.post(`/conversations/${accountId}/${threadId}/restore`)
export const getDailyStats = (accountId, days = 7) =>
  api.get(`/stats/${accountId}/daily`, { params: { days } })
export const getSummary = (accountId) => api.get(`/stats/${accountId}/summary`)

// Triggers
export const getTriggers = (accountId) => api.get(`/triggers/${accountId}`)
export const createTrigger = (accountId, data) => api.post(`/triggers/${accountId}`, data)
export const updateTrigger = (accountId, triggerId, data) => api.put(`/triggers/${accountId}/${triggerId}`, data)
export const deleteTrigger = (accountId, triggerId) => api.delete(`/triggers/${accountId}/${triggerId}`)

// Outbound
export const getOutboundTargets = (accountId) => api.get(`/outbound/${accountId}`)
export const addOutboundTarget = (accountId, data) => api.post(`/outbound/${accountId}`, data)
export const deleteOutboundTarget = (accountId, targetId) => api.delete(`/outbound/${accountId}/${targetId}`)
