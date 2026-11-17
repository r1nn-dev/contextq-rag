import { Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { RequireAuth } from '@/components/layout/RequireAuth'
import { AuthProvider } from '@/components/providers/AuthProvider'
import { ConversationListProvider } from '@/components/providers/ConversationListProvider'
import { GuestUsageProvider } from '@/components/providers/GuestUsageProvider'
import { SourcesProvider } from '@/components/providers/SourcesProvider'
import { ChatPage } from '@/pages/ChatPage'
import { HistoryPage } from '@/pages/HistoryPage'
import { LandingPage } from '@/pages/LandingPage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { SignupPage } from '@/pages/SignupPage'

function App(): JSX.Element {
  return (
    <AuthProvider>
      <SourcesProvider>
        <GuestUsageProvider>
          <ConversationListProvider>
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/signup" element={<SignupPage />} />
              <Route element={<AppLayout />}>
                {/* one route for new and saved conversations, so the URL can change mid-stream */}
                <Route path="/chat/:conversationId?" element={<ChatPage />} />
                <Route
                  path="/history"
                  element={
                    <RequireAuth>
                      <HistoryPage />
                    </RequireAuth>
                  }
                />
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </ConversationListProvider>
        </GuestUsageProvider>
      </SourcesProvider>
    </AuthProvider>
  )
}

export default App
