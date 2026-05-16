import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  headers: { 'Content-Type': 'application/json' },
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
export const getBotStatus = (accountId) => api.get(`/bot/${accountId}/status`)
export const getBotConfig = (accountId) => api.get(`/bot/${accountId}/config`)
export const pauseBot = (accountId) => api.post(`/bot/${accountId}/pause`)
export const resumeBot = (accountId) => api.post(`/bot/${accountId}/resume`)
export const updateConfig = (accountId, data) => api.put(`/bot/${accountId}/config`, data)
export const getConversations = (accountId, stage) =>
  api.get(`/conversations/${accountId}`, { params: stage ? { stage } : {} })
export const getConversation = (accountId, threadId) =>
  api.get(`/conversations/${accountId}/${threadId}`)
export const takeoverConversation = (threadId) =>
  api.post(`/conversations/${threadId}/takeover`)
export const restoreBot = (threadId) =>
  api.post(`/conversations/${threadId}/restore`)
export const getDailyStats = (accountId, days = 7) =>
  api.get(`/stats/${accountId}/daily`, { params: { days } })
export const getSummary = (accountId) => api.get(`/stats/${accountId}/summary`)
