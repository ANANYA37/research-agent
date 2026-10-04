import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ErrorBoundary } from 'react-error-boundary';
import { Toaster } from 'sonner';
import ErrorFallback from './components/ErrorFallback';
import Header from './components/Header';
import Home from './pages/Home';
import Research from './pages/Research';
import Library from './pages/Library';
import ReportDetail from './pages/ReportDetail';
import Watchlists from './pages/Watchlists';
import Settings from './pages/Settings';
import Auth from './pages/Auth';
import Chat from './pages/Chat';
import { useAuth } from './auth/AuthContext';

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <main className="auth-page">Loading workspace...</main>;
  return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <ErrorBoundary FallbackComponent={ErrorFallback}>
      <Router>
        <Routes>
          <Route path="/login" element={<Auth mode="login" />} />
          <Route path="/register" element={<Auth mode="register" />} />
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ProtectedRoute><><Header /><Chat /></></ProtectedRoute>} />
          <Route path="/dashboard" element={<Navigate to="/chat" replace />} />
          <Route path="/research" element={<ProtectedRoute><><Header /><Research /></></ProtectedRoute>} />
          <Route path="/library" element={<ProtectedRoute><><Header /><Library /></></ProtectedRoute>} />
          <Route path="/reports/:id" element={<ProtectedRoute><><Header /><ReportDetail /></></ProtectedRoute>} />
          <Route path="/watchlists" element={<ProtectedRoute><><Header /><Watchlists /></></ProtectedRoute>} />
          <Route path="/watchlists/:id" element={<ProtectedRoute><><Header /><Watchlists /></></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><><Header /><Settings /></></ProtectedRoute>} />
        </Routes>
        <Toaster richColors position="top-right" />
      </Router>
    </ErrorBoundary>
  );
}
