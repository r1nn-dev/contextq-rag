import { Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { GuestUsageProvider } from '@/components/providers/GuestUsageProvider'
import { SourcesProvider } from '@/components/providers/SourcesProvider'
import { ChatPage } from '@/pages/ChatPage'
import { LandingPage } from '@/pages/LandingPage'
import { NotFoundPage } from '@/pages/NotFoundPage'

function App(): JSX.Element {
  return (
    <SourcesProvider>
      <GuestUsageProvider>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route element={<AppLayout />}>
            <Route path="/chat" element={<ChatPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </GuestUsageProvider>
    </SourcesProvider>
  )
}

export default App
