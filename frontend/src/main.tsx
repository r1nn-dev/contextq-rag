import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

// '!' non-null assertion: <div id="root"> is guaranteed to exist in index.html
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)