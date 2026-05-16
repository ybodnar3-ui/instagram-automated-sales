import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Dashboard from './pages/Dashboard'
import Conversations from './pages/Conversations'
import Stats from './pages/Stats'
import Settings from './pages/Settings'

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-64 text-gray-400">
      <p className="text-5xl font-bold mb-4">404</p>
      <p className="text-lg">Page not found</p>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        <Navbar />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/conversations" element={<Conversations />} />
          <Route path="/stats" element={<Stats />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
