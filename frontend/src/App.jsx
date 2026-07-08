import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { hasCredentials } from './api/client'
import { FilterProvider } from './context/FilterContext'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import HotelDetail from './pages/HotelDetail'

function RequireAuth({ children }) {
  return hasCredentials() ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <FilterProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
          <Route path="/hotels/:id" element={<RequireAuth><HotelDetail /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </FilterProvider>
  )
}
