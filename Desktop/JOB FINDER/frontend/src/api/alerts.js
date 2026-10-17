import api from './client'

const UID = 'default'

export async function fetchAlerts() {
  const { data } = await api.get('/api/alerts/', { params: { user_id: UID } })
  return data
}

export async function createAlert(payload) {
  const { data } = await api.post('/api/alerts/', payload, { params: { user_id: UID } })
  return data
}

export async function updateAlert(id, patch) {
  const { data } = await api.patch(`/api/alerts/${id}`, patch, { params: { user_id: UID } })
  return data
}

export async function deleteAlert(id) {
  await api.delete(`/api/alerts/${id}`, { params: { user_id: UID } })
}

export async function fetchAlertResults(id, { unseenOnly = false } = {}) {
  const { data } = await api.get(`/api/alerts/${id}/results`, {
    params: { user_id: UID, unseen_only: unseenOnly },
  })
  return data
}

export async function markResultSeen(alertId, notificationId) {
  const { data } = await api.patch(
    `/api/alerts/${alertId}/results/${notificationId}/seen`,
    null,
    { params: { user_id: UID } },
  )
  return data
}

export async function runAlertCheck(id) {
  const { data } = await api.post(`/api/alerts/${id}/check`, null, {
    params: { user_id: UID },
  })
  return data
}
