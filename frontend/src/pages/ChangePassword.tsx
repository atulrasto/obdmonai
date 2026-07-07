import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { changePassword } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import PasswordInput from '../components/PasswordInput'

export default function ChangePassword() {
  const [current, setCurrent]   = useState('')
  const [next, setNext]         = useState('')
  const [confirm, setConfirm]   = useState('')
  const [error, setError]       = useState<string | null>(null)
  const [success, setSuccess]   = useState(false)
  const [loading, setLoading]   = useState(false)
  const { role, mustChangePassword, setToken } = useAuth()
  const navigate = useNavigate()

  const forced = mustChangePassword   // true = forced by system, false = voluntary

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (next !== confirm) { setError('New passwords do not match.'); return }
    if (next.length < 8)  { setError('New password must be at least 8 characters.'); return }
    setError(null)
    setLoading(true)
    try {
      const resp = await changePassword(current, next)
      setToken(resp.access_token)
      if (forced) {
        navigate(role === 'superadmin' ? '/admin' : '/', { replace: true })
      } else {
        setSuccess(true)
        setCurrent(''); setNext(''); setConfirm('')
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to change password.')
    } finally {
      setLoading(false)
    }
  }

  function handleCancel() {
    navigate(role === 'superadmin' ? '/admin' : '/', { replace: true })
  }

  return (
    <div className="login-wrap">
      <div className="login-box">
        <div className="login-title">⬡ obdmonai</div>

        {forced ? (
          <p style={{ fontSize: '0.85rem', color: '#dc2626', marginBottom: '1.25rem', fontWeight: 500 }}>
            You must set a new password before continuing.
          </p>
        ) : (
          <p style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '1.25rem' }}>
            Change your account password.
          </p>
        )}

        {success && (
          <div style={{
            background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 6,
            padding: '0.65rem 0.85rem', marginBottom: '1rem',
            fontSize: '0.85rem', color: '#166534', fontWeight: 500,
          }}>
            ✓ Password changed successfully.
          </div>
        )}

        {error && <div className="error-msg">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="current">Current password</label>
            <PasswordInput
              id="current"
              autoComplete="current-password"
              value={current}
              onChange={setCurrent}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="next">New password</label>
            <PasswordInput
              id="next"
              autoComplete="new-password"
              value={next}
              onChange={setNext}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="confirm">Confirm new password</label>
            <PasswordInput
              id="confirm"
              autoComplete="new-password"
              value={confirm}
              onChange={setConfirm}
              required
            />
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
            <button className="btn btn-primary" type="submit" disabled={loading}
              style={{ flex: 1 }}>
              {loading ? 'Saving…' : 'Set new password'}
            </button>
            {!forced && (
              <button type="button" className="btn btn-secondary" onClick={handleCancel}>
                Cancel
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  )
}
