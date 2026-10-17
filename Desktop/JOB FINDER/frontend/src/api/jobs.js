import api from './client'

export function normalizeJob(j) {
  return {
    id: j.id,
    title: j.title,
    company: j.company,
    initials: j.initials ?? j.company?.slice(0, 2).toUpperCase() ?? '??',
    color: j.color ?? '#4F46E5',
    location: j.location ?? '',
    locationType: j.location_type ?? 'On-site',
    type: j.type ?? 'Full-time',
    experience: j.experience ?? 'Mid',
    salary: j.salary ?? '',
    matchScore: j.match_score ?? 0,
    source: j.source ?? 'linkedin',
    postedDays: j.posted_days ?? 0,
    description: j.description ?? '',
    requirements: j.requirements ?? [],
    matchingSkills: j.matching_skills ?? [],
    missingSkills: j.missing_skills ?? [],
    tags: j.tags ?? [],
    applied: false,
  }
}

export async function fetchJobs(params = {}) {
  const { data } = await api.get('/api/jobs/', { params })
  return { ...data, jobs: data.jobs.map(normalizeJob) }
}

export async function fetchJob(id) {
  const { data } = await api.get(`/api/jobs/${id}`)
  return normalizeJob(data)
}
