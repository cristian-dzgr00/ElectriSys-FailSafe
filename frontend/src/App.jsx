import { lazy, Suspense, useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Sidebar from './components/Sidebar';
import Navbar  from './components/Navbar';

const Login        = lazy(() => import('./pages/Login'));
const Dashboard    = lazy(() => import('./pages/Dashboard'));
const Repuestos    = lazy(() => import('./pages/Repuestos'));
const Proveedores  = lazy(() => import('./pages/Proveedores'));
const Pedidos      = lazy(() => import('./pages/Pedidos'));
const Ventas       = lazy(() => import('./pages/Ventas'));
const Cotizaciones = lazy(() => import('./pages/Cotizaciones'));
const Clientes     = lazy(() => import('./pages/Clientes'));
const Reportes     = lazy(() => import('./pages/Reportes'));
const Usuarios     = lazy(() => import('./pages/Usuarios'));
const Auditoria    = lazy(() => import('./pages/Auditoria'));
const Backups      = lazy(() => import('./pages/Backups'));

function PageFallback() {
  return (
    <div style={{ padding: 28 }}>
      {[80, 60, 70, 50, 65].map((w, i) => (
        <div key={i} style={{
          height: 14, marginBottom: 14, borderRadius: 6,
          width: `${w}%`,
          background: 'linear-gradient(90deg, var(--bg-hover) 25%, var(--bg-card) 50%, var(--bg-hover) 75%)',
          backgroundSize: '200% 100%', animation: 'shimmer 1.4s infinite',
        }} />
      ))}
    </div>
  );
}

function PrivateRoute({ children, adminOnly = false, duenoOnly = false, roles = null }) {
  const { user, loading, isAdmin } = useAuth();
  const isDueno = () => user?.rol === 'dueno';
  if (loading) return <PageFallback />;
  if (!user)   return <Navigate to="/login" replace />;
  // `roles` cubre las pantallas compartidas por varios roles (ej. Pedidos,
  // que es de admin Y dueno): adminOnly/duenoOnly solo aceptan uno cada uno.
  if (roles && !roles.includes(user.rol)) return <Navigate to="/" replace />;
  if (duenoOnly && !isDueno()) return <Navigate to="/" replace />;
  if (adminOnly && !isAdmin()) return <Navigate to="/" replace />;
  return children;
}

function AppLayout() {
  // Solo importa en el drawer móvil (ver la media query de 768px en
  // index.css) — en escritorio el sidebar ignora esta clase y queda
  // siempre visible en su columna.
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="app-layout">
      <Sidebar open={sidebarOpen} onNavigate={() => setSidebarOpen(false)} />
      <div
        className={`sidebar-backdrop ${sidebarOpen ? 'sidebar-backdrop-open' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />
      <div className="main-content">
        <Navbar onToggleSidebar={() => setSidebarOpen(o => !o)} />
        <div className="page-body">
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="/"              element={<Dashboard />} />
              <Route path="/repuestos"     element={<Repuestos />} />
              <Route path="/ventas"        element={<Ventas />} />
              <Route path="/cotizaciones"  element={<Cotizaciones />} />
              <Route path="/clientes"      element={<Clientes />} />
              <Route path="/proveedores"   element={<PrivateRoute adminOnly><Proveedores /></PrivateRoute>} />
              <Route path="/pedidos"       element={<PrivateRoute roles={['admin','dueno']}><Pedidos /></PrivateRoute>} />
              <Route path="/reportes"      element={<PrivateRoute adminOnly><Reportes /></PrivateRoute>} />
              <Route path="/usuarios"      element={<PrivateRoute adminOnly><Usuarios /></PrivateRoute>} />
              <Route path="/auditoria"     element={<PrivateRoute duenoOnly><Auditoria /></PrivateRoute>} />
              <Route path="/backups"       element={<PrivateRoute roles={['admin','dueno']}><Backups /></PrivateRoute>} />
            </Routes>
          </Suspense>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <PageFallback />;
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
        <Route path="/*"     element={<PrivateRoute><AppLayout /></PrivateRoute>} />
      </Routes>
    </Suspense>
  );
}