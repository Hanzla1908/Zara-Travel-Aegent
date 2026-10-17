import api from './client'

const UID = 'default'

export async function uploadCV(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/api/cv/upload', form, {
    params: { user_id: UID },
  })
  return data
}

export async function getProfile() {
  const { data } = await api.get('/api/cv/profile', { params: { user_id: UID } })
  return data
}

export async function getMatches({ explain = false, limit = 20, skillsWeight, experienceWeight, titleWeight, locationWeight } = {}) {
  const params = { user_id: UID, explain, limit }
  if (skillsWeight !== undefined)     params.skills_weight     = skillsWeight
  if (experienceWeight !== undefined) params.experience_weight = experienceWeight
  if (titleWeight !== undefined)      params.title_weight      = titleWeight
  if (locationWeight !== undefined)   params.location_weight   = locationWeight
  const { data } = await api.get('/api/cv/matches', { params })
  return data
}
