import { Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { AuthProvider } from '@/components/providers/AuthProvider'
import { GuestUsageProvider } from '@/components/providers/GuestUsageProvider'
import { SourcesProvider } from '@/components/providers/SourcesProvider'
import { ChatPage } from '@/pages/ChatPage'
import { LandingPage } from '@/pages/LandingPage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { SignupPage } from '@/pages/SignupPage'

function App(): JSX.Element {
  return (
    <AuthProvider>
      <SourcesProvider>
        <GuestUsageProvider>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route element={<AppLayout />}>
              <Route path="/chat" element={<ChatPage />} />
            </Route>
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </GuestUsageProvider>
      </SourcesProvider>
    </AuthProvider>
  )
}

export default App
