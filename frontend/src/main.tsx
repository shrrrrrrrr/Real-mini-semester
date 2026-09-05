import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import './index.css'
import { AppShell } from './components/AppShell'
import { ToastProvider } from './components/Toast'
import { ThemeProvider } from './lib/theme'
import { ChatPage } from './pages/Chat'
import { ExplainPage } from './pages/Explain'
import { LibraryPage } from './pages/Library'
import { QuizPage } from './pages/Quiz'
import { ReviewPage } from './pages/Review'
import { StatsPage } from './pages/Stats'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <ToastProvider>
        <HashRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/" element={<Navigate to="/library" replace />} />
              <Route path="/library" element={<LibraryPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/explain" element={<ExplainPage />} />
              <Route path="/quiz" element={<QuizPage />} />
              <Route path="/review" element={<ReviewPage />} />
              <Route path="/stats" element={<StatsPage />} />
            </Route>
          </Routes>
        </HashRouter>
      </ToastProvider>
    </ThemeProvider>
  </StrictMode>,
)
