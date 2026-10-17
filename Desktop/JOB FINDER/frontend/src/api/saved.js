import api from './client'
import { normalizeJob } from './jobs'

const UID = 'default'

export async function fetchSavedIds() {
  const { data } = await api.get('/api/saved/', { params: { user_id: UID } })
  return new Set(data.map(j => j.id))
}

export async function fetchSavedJobs() {
  const { data } = await api.get('/api/saved/', { params: { user_id: UID } })
  return data.map(normalizeJob)
}

export async function saveJob(id) {
  await api.post(`/api/saved/${id}`, null, { params: { user_id: UID } })
}

export async function unsaveJob(id) {
  await api.delete(`/api/saved/${id}`, { params: { user_id: UID } })
}
