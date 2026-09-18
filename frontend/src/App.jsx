import { useEffect, useState } from 'react'
import './App.css'

// The dashboard is generated as a standalone page by
// `src/generate_dashboard_preview.py` into `public/`, so Vite serves it in dev
// and bundles it into `dist` for `npm run preview`. The app frames that page.
const PREVIEW_URL = '/dashboard_preview.html'

function App() {
  const [status, setStatus] = useState('checking')

  useEffect(() => {
    let cancelled = false
    fetch(PREVIEW_URL, { method: 'HEAD' })
      .then((response) => {
        if (!cancelled) setStatus(response.ok ? 'ready' : 'missing')
      })
      .catch(() => {
        if (!cancelled) setStatus('missing')
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (status === 'checking') {
    return <main className="preview-status">Loading dashboard preview...</main>
  }

  if (status === 'missing') {
    return (
      <main className="preview-status">
        <h1>Dashboard preview not generated yet</h1>
        <p>Run this from the project root, then reload:</p>
        <code>python src/generate_dashboard_preview.py</code>
      </main>
    )
  }

  return (
    <iframe
      className="preview-frame"
      title="Student Dropout Risk dashboard preview"
      src={PREVIEW_URL}
    />
  )
}

export default App
