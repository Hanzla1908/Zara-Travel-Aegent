import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '',
  paramsSerializer: {
    serialize(params) {
      const parts = []
      for (const [k, v] of Object.entries(params)) {
        if (Array.isArray(v)) {
          v.forEach(x => parts.push(`${k}=${encodeURIComponent(x)}`))
        } else if (v !== undefined && v !== null && v !== '') {
          parts.push(`${k}=${encodeURIComponent(v)}`)
        }
      }
      return parts.join('&')
    },
  },
})

export default api
