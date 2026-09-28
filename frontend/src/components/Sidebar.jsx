import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard, Wrench, Truck, ShoppingCart,
  FileText, Users, BarChart2, UserCog, ShieldCheck, ClipboardList, DatabaseBackup
} from 'lucide-react';
import OnboardingTour from './OnboardingTour';
import logo from '../assets/logo.png';

const adminLinks = [
  { to: '/',             icon: LayoutDashboard, label: 'Dashboard',     id: 'nav-dashboard' },
  { to: '/repuestos',    icon: Wrench,           label: 'Repuestos',     id: 'nav-repuestos' },
  { to: '/proveedores',  icon: Truck,            label: 'Proveedores',   id: 'nav-proveedores' },
  { to: '/pedidos',      icon: ClipboardList,     label: 'Pedidos',       id: 'nav-pedidos' },
  { to: '/ventas',       icon: ShoppingCart,     label: 'Ventas',        id: 'nav-ventas' },
  { to: '/cotizaciones', icon: FileText,          label: 'Cotizaciones',  id: 'nav-cotizaciones' },
  { to: '/clientes',     icon: Users,             label: 'Clientes',      id: 'nav-clientes' },
  { to: '/reportes',     icon: BarChart2,         label: 'Reportes',      id: 'nav-reportes' },
  { to: '/usuarios',     icon: UserCog,           label: 'Usuarios',      id: 'nav-usuarios' },
  { to: '/backups',      icon: DatabaseBackup,    label: 'Respaldos',     id: 'nav-backups' },
];

const duenroLinks = [
  { to: '/',             icon: LayoutDashboard, label: 'Dashboard',     id: 'nav-dashboard' },
  { to: '/repuestos',    icon: Wrench,           label: 'Repuestos',     id: 'nav-repuestos' },
  { to: '/proveedores',  icon: Truck,            label: 'Proveedores',   id: 'nav-proveedores' },
  { to: '/pedidos',      icon: ClipboardList,     label: 'Pedidos',       id: 'nav-pedidos' },
  { to: '/ventas',       icon: ShoppingCart,     label: 'Ventas',        id: 'nav-ventas' },
  { to: '/cotizaciones', icon: FileText,          label: 'Cotizaciones',  id: 'nav-cotizaciones' },
  { to: '/clientes',     icon: Users,             label: 'Clientes',      id: 'nav-clientes' },
  { to: '/reportes',     icon: BarChart2,         label: 'Reportes',      id: 'nav-reportes' },
  { to: '/usuarios',     icon: UserCog,           label: 'Usuarios',      id: 'nav-usuarios' },
  { to: '/backups',      icon: DatabaseBackup,    label: 'Respaldos',     id: 'nav-backups' },
  { to: '/auditoria',    icon: ShieldCheck,       label: 'Auditoría',     id: 'nav-auditoria' },
];

const vendedorLinks = [
  { to: '/repuestos',    icon: Wrench,       label: 'Repuestos',    id: 'nav-repuestos' },
  { to: '/ventas',       icon: ShoppingCart, label: 'Ventas',       id: 'nav-ventas' },
  { to: '/cotizaciones', icon: FileText,     label: 'Cotizaciones', id: 'nav-cotizaciones' },
  { to: '/clientes',     icon: Users,        label: 'Clientes',     id: 'nav-clientes' },
];

export default function Sidebar({ open = false, onNavigate }) {
  const { user, isAdmin } = useAuth();
  const isDueno = () => user?.rol === 'dueno';
  const links = isDueno() ? duenroLinks : isAdmin() ? adminLinks : vendedorLinks;

  return (
    <>
      {/* Tour aparece una sola vez para usuarios nuevos */}
      <OnboardingTour />

      {/* sidebar-open solo hace algo dentro de la media query móvil de
          index.css (drawer superpuesto); en escritorio no tiene efecto. */}
      <aside className={`sidebar ${open ? 'sidebar-open' : ''}`} style={{
        width: 'var(--sidebar-width)',
        background: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
        height: '100vh',
        overflowY: 'auto',
      }}>
        {/* Logo */}
        <div style={{
          padding: '20px 18px 16px',
          borderBottom: '1px solid var(--border)',
        }}>
          <img
            src={logo}
            alt="ElectriSys · Electritorres"
            style={{ width: '100%', height: 'auto', display: 'block' }}
          />
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '12px 10px' }}>
          {links.map(({ to, icon: Icon, label, id }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              id={id}
              onClick={() => onNavigate?.()}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '9px 12px',
                borderRadius: 'var(--radius)',
                marginBottom: 2,
                color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                background: isActive ? 'var(--accent-dim)' : 'transparent',
                fontWeight: isActive ? 600 : 400,
                fontSize: 13,
                textDecoration: 'none',
                transition: 'all var(--transition)',
                borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
              })}
            >
              {({ isActive }) => (
                <>
                  <Icon size={16} strokeWidth={isActive ? 2.5 : 1.8} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div style={{
          padding: '12px 18px',
          borderTop: '1px solid var(--border)',
          fontSize: 11,
          color: 'var(--text-muted)',
        }}>
          ElectriSys v2.0 · {new Date().getFullYear()}
        </div>
      </aside>
    </>
  );
}