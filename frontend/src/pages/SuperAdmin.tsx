import { useEffect, useState, type FormEvent } from 'react'
import { listAllClients, adminCreateClient } from '../api/client'
import type { ClientRead, ClientCreateResponse } from '../api/types'

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString([], { dateStyle: 'medium' })
}

export default function SuperAdmin() {
  const [clients, setClients] = useState<ClientRead[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [ownerEmail, setOwnerEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<ClientCreateResponse | null>(null)

  async function reload() {
    const data = await listAllClients()
    setClients(data)
  }

  useEffect(() => {
    reload().finally(() => setLoading(false))
  }, [])

  function autoSlug(n: string) {
    return n.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const result = await adminCreateClient({ name, slug, owner_email: ownerEmail })
      setCreated(result)
      setName('')
      setSlug('')
      setOwnerEmail('')
      setShowForm(false)
      await reload()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Failed to create client.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Clients Management</h1>
        <button className="btn btn-primary" onClick={() => { setShowForm(!showForm); setCreated(null); setError(null) }}>
          {showForm ? 'Cancel' : '+ New client'}
        </button>
      </div>

      {created && (
        <div className="card" style={{ marginBottom: '1.5rem', border: '1px solid #bbf7d0', background: '#f0fdf4' }}>
          <div style={{ fontWeight: 600, marginBottom: '0.5rem', color: '#166534' }}>Client created successfully</div>
          <div style={{ fontSize: '0.85rem', color: '#15803d', lineHeight: 1.8 }}>
            <div><strong>Tenant:</strong> {created.name} ({created.slug})</div>
            <div><strong>Owner email:</strong> {created.owner_email}</div>
            <div>
              <strong>Temp password:</strong>{' '}
              <code style={{ background: '#dcfce7', padding: '0.1rem 0.4rem', borderRadius: 4, fontFamily: 'monospace' }}>
                {created.temp_password}
              </code>
              <span style={{ fontSize: '0.75rem', color: '#64748b', marginLeft: 8 }}>
                (shown once — also emailed to owner)
              </span>
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '0.9rem', marginBottom: '1rem' }}>Create new client</h3>
          {error && <div className="error-msg">{error}</div>}
          <form onSubmit={handleCreate}>
            <div className="form-group">
              <label>Company name</label>
              <input
                value={name}
                onChange={(e) => { setName(e.target.value); setSlug(autoSlug(e.target.value)) }}
                placeholder="Acme Logistics"
                required
              />
            </div>
            <div className="form-group">
              <label>Slug (URL-safe, unique)</label>
              <input
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="acme-logistics"
                pattern="[a-z0-9\-]+"
                required
              />
            </div>
            <div className="form-group">
              <label>Owner email</label>
              <input
                type="text"
                value={ownerEmail}
                onChange={(e) => setOwnerEmail(e.target.value)}
                placeholder="admin@acmelogistics.com"
                required
              />
            </div>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? 'Creating…' : 'Create client'}
            </button>
          </form>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>Loading…</div>
        ) : clients.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>No clients yet</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Slug</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr key={c.id}>
                  <td style={{ fontWeight: 500 }}>{c.name}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: '#64748b' }}>{c.slug}</td>
                  <td>
                    <span className={`badge ${c.is_active ? 'badge-cleared' : 'badge-warning'}`}>
                      {c.is_active ? 'active' : 'inactive'}
                    </span>
                  </td>
                  <td style={{ fontSize: '0.8rem', color: '#64748b' }}>{fmtDate(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
