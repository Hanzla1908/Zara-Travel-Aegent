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
