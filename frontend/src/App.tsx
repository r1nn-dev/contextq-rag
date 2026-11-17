import { Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { GuestUsageProvider } from '@/components/providers/GuestUsageProvider'
import { SourcesProvider } from '@/components/providers/SourcesProvider'
import { LandingPage } from '@/pages/LandingPage'
import { NotFoundPage } from '@/pages/NotFoundPage'

function App(): JSX.Element {
  return (
    <SourcesProvider>
      <GuestUsageProvider>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route element={<AppLayout />}>
            <Route path="/chat" element={<div className="center-fill">채팅 화면</div>} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </GuestUsageProvider>
    </SourcesProvider>
  )
}

export default App
