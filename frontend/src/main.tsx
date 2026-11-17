import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { setTransport } from '@/api/http'
import App from './App'
import '@/styles/base.css'
import '@/styles/layout.css'

async function bootstrap(): Promise<void> {
  // development mock; the dynamic import keeps it out of production bundles
  if (import.meta.env.VITE_USE_MOCK === 'true') {
    const { mockFetch } = await import('./mocks')
    setTransport(mockFetch)
  }

  // '!' non-null assertion: <div id="root"> is guaranteed to exist in index.html
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </StrictMode>,
  )
}

void bootstrap()
