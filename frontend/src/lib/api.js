const API_BASE = import.meta.env.VITE_API_URL || ''

export async function API(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) throw new Error(res.statusText)
  return res.json()
}
