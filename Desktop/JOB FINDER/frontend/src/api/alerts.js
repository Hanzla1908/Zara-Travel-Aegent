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
