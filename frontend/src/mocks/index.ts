// Entry point of the development mock. Loaded by main.tsx only when VITE_USE_MOCK=true,
// through a dynamic import so production bundles do not include it.

import './handlers/auth'
import './handlers/sources'
import './handlers/chat'
import './handlers/conversations'

export { mockFetch } from './router'
