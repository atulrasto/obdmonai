import { useState } from 'react'

interface Props {
  id: string
  value: string
  onChange: (v: string) => void
  autoComplete?: string
  required?: boolean
  placeholder?: string
}

export default function PasswordInput({ id, value, onChange, autoComplete, required, placeholder }: Props) {
  const [show, setShow] = useState(false)
  return (
    <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
      <input
        id={id}
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        required={required}
        placeholder={placeholder}
        style={{ paddingRight: '2.5rem', width: '100%', boxSizing: 'border-box' }}
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        tabIndex={-1}
        aria-label={show ? 'Hide password' : 'Show password'}
        style={{
          position: 'absolute', right: '0.6rem',
          background: 'none', border: 'none', cursor: 'pointer',
          color: '#94a3b8', fontSize: '1rem', lineHeight: 1, padding: '0.2rem',
          userSelect: 'none',
        }}
      >
        {show ? '🙈' : '👁'}
      </button>
    </div>
  )
}
