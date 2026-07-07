import { useRef, useState } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type FlashStep = 'idle' | 'connecting' | 'flashing' | 'done' | 'error'

interface Props {
  deviceId: string
  deviceSerial: string
  onClose: () => void
}

// ── Constants ─────────────────────────────────────────────────────────────────

const PRESETS = [
  { label: 'Application — 0x10000 (recommended)', value: '0x10000' },
  { label: 'Bootloader  — 0x1000  (danger!)',      value: '0x1000'  },
  { label: 'Partitions  — 0x8000  (danger!)',      value: '0x8000'  },
  { label: 'Full chip   — 0x0',                    value: '0x0'     },
]

const BAUD_RATES = ['115200', '460800', '921600']

// ── Component ─────────────────────────────────────────────────────────────────

export default function FlashModal({ deviceSerial, onClose }: Props) {
  const [step, setStep]         = useState<FlashStep>('idle')
  const [log, setLog]           = useState<string[]>([])
  const [progress, setProgress] = useState(0)
  const [fileName, setFileName] = useState<string | null>(null)
  const [flashAddr, setFlashAddr] = useState('0x10000')
  const [baudRate, setBaudRate] = useState('921600')

  const fileRef      = useRef<File | null>(null)
  const transportRef = useRef<any>(null)
  const logBoxRef    = useRef<HTMLDivElement>(null)

  const push = (line: string) => {
    setLog((prev) => [...prev, line])
    requestAnimationFrame(() => {
      if (logBoxRef.current)
        logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight
    })
  }

  const isBusy = step === 'connecting' || step === 'flashing'

  // ── Core flash routine ────────────────────────────────────────────────────

  async function runFlash() {
    const file = fileRef.current
    if (!file) { push('❌ Select a .bin file first.'); return }

    if (!('serial' in navigator)) {
      setLog([
        '❌ Web Serial API is not available in this browser.',
        '   Please use Google Chrome or Microsoft Edge (not Firefox/Safari).',
        '   Also make sure the page is served over HTTPS or localhost.',
      ])
      setStep('error')
      return
    }

    setLog([])
    setProgress(0)
    setStep('connecting')

    let transport: any = null

    try {
      // Dynamic import — only loaded when the user actually flashes
      const { ESPLoader, Transport } = await import('esptool-js')

      const terminal = {
        clean:     () => {},
        writeLine: (data: string) => push(data),
        write:     (data: string) => setLog((prev) => {
          if (!prev.length) return [data]
          const lines = [...prev]
          lines[lines.length - 1] += data
          return lines
        }),
      }

      push('📡 Select the ESP32 USB-Serial port in the browser dialog...')
      const port = await (navigator as any).serial.requestPort()
      transport = new Transport(port, true)
      transportRef.current = transport

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const loader = new ESPLoader({ transport, baudrate: 115200, terminal } as any)

      push('🔌 Syncing with ESP32 bootloader...')
      const chip = await loader.main()
      push(`✅ Chip identified: ${chip}`)

      // Read .bin into Latin-1 binary string (esptool-js format)
      push(`📂 Reading "${file.name}" (${(file.size / 1024).toFixed(1)} KB)...`)
      const buf   = await file.arrayBuffer()
      const bytes = new Uint8Array(buf)
      let binary  = ''
      for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])

      const address = parseInt(flashAddr, 16)
      push(`⚡ Flashing to ${flashAddr} — please wait...`)
      setStep('flashing')

      await loader.writeFlash({
        fileArray:   [{ data: binary, address }],
        flashSize:   'keep',
        flashMode:   'keep',
        flashFreq:   'keep',
        eraseAll:    false,
        compress:    true,
        reportProgress: (_i: number, written: number, total: number) => {
          setProgress(Math.round((written / total) * 100))
        },
      })

      push('🎉 Flash complete!')
      push('🔄 Resetting ESP32...')
      await transport.disconnect()
      transportRef.current = null
      push('✅ Device is running the new firmware. You can close this dialog.')
      setStep('done')

    } catch (err: any) {
      const msg: string = err?.message ?? String(err)
      const cancelled = /cancel|no port|user gestured|not selected/i.test(msg)
      if (cancelled) {
        push('ℹ️ Port selection was cancelled.')
        setStep('idle')
      } else {
        push(`❌ ${msg}`)
        setStep('error')
      }
      try { await transport?.disconnect() } catch { /* ignore */ }
      transportRef.current = null
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const stepColor: Record<FlashStep, string> = {
    idle:       '#6366f1',
    connecting: '#f59e0b',
    flashing:   '#0ea5e9',
    done:       '#10b981',
    error:      '#dc2626',
  }
  const stepLabel: Record<FlashStep, string> = {
    idle:       'Ready',
    connecting: 'Connecting…',
    flashing:   `Flashing ${progress}%`,
    done:       'Done',
    error:      'Error',
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(15,23,42,0.55)', backdropFilter: 'blur(3px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#fff', borderRadius: 12, width: 560, maxWidth: '95vw',
        boxShadow: '0 20px 60px rgba(0,0,0,0.18)', overflow: 'hidden',
      }}>
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div style={{
          background: '#0f172a', color: '#f1f5f9',
          padding: '1rem 1.25rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '1rem' }}>Flash ESP32 Firmware</div>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontFamily: 'monospace' }}>
              Device: {deviceSerial}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{
              padding: '0.2rem 0.6rem', borderRadius: 999, fontSize: '0.72rem', fontWeight: 600,
              background: stepColor[step] + '25', color: stepColor[step],
              border: `1px solid ${stepColor[step]}50`,
            }}>
              {stepLabel[step]}
            </span>
            <button onClick={onClose} disabled={isBusy}
              style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: isBusy ? 'not-allowed' : 'pointer', fontSize: '1.1rem' }}>
              ✕
            </button>
          </div>
        </div>

        <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>

          {/* ── Browser warning ─────────────────────────────────────────── */}
          <div style={{
            background: '#fefce8', border: '1px solid #fde68a', borderRadius: 6,
            padding: '0.6rem 0.75rem', fontSize: '0.78rem', color: '#78350f',
          }}>
            <strong>Requires Chrome / Edge</strong> — Web Serial API is not supported in Firefox or Safari.
            The ESP32 must be connected via USB to <em>this computer</em>.
          </div>

          {/* ── Config row ──────────────────────────────────────────────── */}
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 280px' }}>
              <label style={{ fontSize: '0.78rem', fontWeight: 600, color: '#475569', display: 'block', marginBottom: '0.25rem' }}>
                Flash address
              </label>
              <select value={flashAddr} onChange={(e) => setFlashAddr(e.target.value)} disabled={isBusy}
                style={{ width: '100%', padding: '0.4rem 0.5rem', borderRadius: 6, border: '1.5px solid #e2e8f0', fontSize: '0.82rem' }}>
                {PRESETS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>
            <div style={{ flex: '0 0 110px' }}>
              <label style={{ fontSize: '0.78rem', fontWeight: 600, color: '#475569', display: 'block', marginBottom: '0.25rem' }}>
                Baud rate
              </label>
              <select value={baudRate} onChange={(e) => setBaudRate(e.target.value)} disabled={isBusy}
                style={{ width: '100%', padding: '0.4rem 0.5rem', borderRadius: 6, border: '1.5px solid #e2e8f0', fontSize: '0.82rem' }}>
                {BAUD_RATES.map((b) => <option key={b}>{b}</option>)}
              </select>
            </div>
          </div>

          {/* ── File picker ─────────────────────────────────────────────── */}
          <div>
            <label style={{ fontSize: '0.78rem', fontWeight: 600, color: '#475569', display: 'block', marginBottom: '0.25rem' }}>
              Firmware binary (.bin)
            </label>
            <div style={{
              border: '2px dashed #cbd5e1', borderRadius: 8, padding: '1rem',
              textAlign: 'center', cursor: 'pointer', background: '#f8fafc',
              transition: 'border-color 0.15s',
            }}>
              <input
                type="file"
                accept=".bin"
                disabled={isBusy}
                style={{ display: 'none' }}
                id="firmware-file"
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null
                  fileRef.current = f
                  setFileName(f?.name ?? null)
                  if (step === 'error') setStep('idle')
                }}
              />
              <label htmlFor="firmware-file" style={{ cursor: isBusy ? 'not-allowed' : 'pointer', display: 'block' }}>
                {fileName ? (
                  <span style={{ fontWeight: 600, color: '#0f172a', fontSize: '0.85rem' }}>
                    📦 {fileName}
                  </span>
                ) : (
                  <span style={{ color: '#64748b', fontSize: '0.82rem' }}>
                    Click to select firmware .bin file
                    <br />
                    <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
                      (PlatformIO: .pio/build/esp32dev/firmware.bin)
                    </span>
                  </span>
                )}
              </label>
            </div>
          </div>

          {/* ── Progress bar ─────────────────────────────────────────────── */}
          {(step === 'flashing' || step === 'done') && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#64748b', marginBottom: '0.3rem' }}>
                <span>Flash progress</span>
                <span>{progress}%</span>
              </div>
              <div style={{ background: '#e2e8f0', borderRadius: 999, height: 8, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 999,
                  background: step === 'done' ? '#10b981' : '#0ea5e9',
                  width: `${progress}%`,
                  transition: 'width 0.2s',
                }} />
              </div>
            </div>
          )}

          {/* ── Terminal log ─────────────────────────────────────────────── */}
          {log.length > 0 && (
            <div ref={logBoxRef} style={{
              background: '#0f172a', borderRadius: 8,
              padding: '0.75rem 1rem', maxHeight: 160, overflowY: 'auto',
              fontFamily: 'monospace', fontSize: '0.76rem', lineHeight: 1.7,
              color: '#e2e8f0',
            }}>
              {log.map((line, i) => (
                <div key={i} style={{
                  color: line.startsWith('❌') ? '#fca5a5'
                       : line.startsWith('✅') ? '#86efac'
                       : line.startsWith('🎉') ? '#fde68a'
                       : '#e2e8f0',
                }}>
                  {line}
                </div>
              ))}
            </div>
          )}

          {/* ── Action buttons ───────────────────────────────────────────── */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
            <button onClick={onClose} disabled={isBusy}
              className="btn btn-secondary" style={{ opacity: isBusy ? 0.4 : 1 }}>
              {step === 'done' ? 'Close' : 'Cancel'}
            </button>
            {step !== 'done' && (
              <button
                onClick={runFlash}
                disabled={isBusy || !fileName}
                className="btn btn-primary"
                style={{ opacity: (isBusy || !fileName) ? 0.5 : 1, minWidth: 140 }}
              >
                {step === 'connecting' ? '🔌 Connecting…'
                 : step === 'flashing' ? `⚡ ${progress}% flashing…`
                 : step === 'error' ? '🔁 Retry'
                 : '⚡ Connect & Flash'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
