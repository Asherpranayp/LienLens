import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import App from './App'
import DocumentsPage from './pages/DocumentsPage'
import MetricsPage from './pages/MetricsPage'
import ReviewPage from './pages/ReviewPage'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route index element={<DocumentsPage />} />
          <Route path="documents/:id" element={<ReviewPage />} />
          <Route path="accuracy" element={<MetricsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
