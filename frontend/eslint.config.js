import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

// frontend/AGENTS.md §1 rules enforced at lint time
const SSE_MESSAGE = 'Use fetch + ReadableStream for SSE; EventSource cannot send Authorization (ADR-003).'
const STORAGE_MESSAGE = 'Keep tokens in memory only; browser storage is forbidden (policy §1.2).'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // warn when a module exports non-components (breaks Fast Refresh)
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      'no-restricted-globals': [
        'error',
        { name: 'EventSource', message: SSE_MESSAGE },
        { name: 'localStorage', message: STORAGE_MESSAGE },
        { name: 'sessionStorage', message: STORAGE_MESSAGE },
      ],
      'no-restricted-properties': [
        'error',
        { object: 'window', property: 'EventSource', message: SSE_MESSAGE },
        { object: 'window', property: 'localStorage', message: STORAGE_MESSAGE },
        { object: 'window', property: 'sessionStorage', message: STORAGE_MESSAGE },
      ],
    },
  },
)