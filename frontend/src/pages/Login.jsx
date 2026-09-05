import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Zap, Eye, EyeOff, ShieldAlert } from 'lucide-react';

export default function Login() {
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [error,    setError]    = useState('');
  const [loading,  setLoading]  = useState(false);
  const { login }  = useAuth();
  const navigate   = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    // Validaciones de cliente antes de llamar al backend
    if (!email.includes('@')) { setError('Ingresa un correo electrónico válido'); return; }
    if (password.length < 4)  { setError('La contraseña es muy corta'); return; }

    setLoading(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err) {
      // El backend ya retorna mensajes amigables (rate limiting, credenciales, etc.)
      setError(err.response?.data?.error || 'No se pudo iniciar sesión. Verifica tus datos.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg-primary)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 20,
    }}>
      {/* Glow de fondo */}
      <div style={{
        position: 'fixed',
        top: '20%', left: '50%',
        transform: 'translateX(-50%)',
        width: 600, height: 600,
        background: 'radial-gradient(circle, rgba(245,166,35,.08) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <div style={{
        width: '100%', maxWidth: 400,
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '36px 32px',
        boxShadow: '0 24px 64px rgba(0,0,0,.5)',
        animation: 'slideUp .3s ease',
      }}>
        {/* Logo y bienvenida */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            width: 52, height: 52,
            background: 'var(--accent)',
            borderRadius: 14,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 14px',
            boxShadow: '0 8px 24px rgba(245,166,35,.3)',
          }}>
            <Zap size={26} color="#111" strokeWidth={2.5} />
          </div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>ElectriSys POS</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
            Sistema de punto de venta para repuestos eléctricos
          </div>
          <div style={{
            marginTop: 10,
            display: 'inline-block',
            background: 'var(--accent-dim)',
            border: '1px solid rgba(245,166,35,.25)',
            borderRadius: 20,
            padding: '3px 12px',
            fontSize: 11,
            color: 'var(--accent)',
            fontWeight: 600,
            letterSpacing: '.03em',
          }}>
            Acceso autorizado únicamente
          </div>
        </div>

        {error && (
          <div className="alert alert-error" style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <ShieldAlert size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Correo electrónico</label>
            <input
              type="email"
              className="form-control"
              placeholder="usuario@empresa.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoFocus
              autoComplete="email"
            />
          </div>

          <div className="form-group" style={{ position: 'relative' }}>
            <label className="form-label">Contraseña</label>
            <input
              type={showPass ? 'text' : 'password'}
              className="form-control"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              style={{ paddingRight: 42 }}
              required
              autoComplete="current-password"
            />
            <button
              type="button"
              onClick={() => setShowPass(p => !p)}
              title={showPass ? 'Ocultar contraseña' : 'Mostrar contraseña'}
              style={{
                position: 'absolute', right: 10, top: 31,
                background: 'none', border: 'none',
                color: 'var(--text-muted)', cursor: 'pointer',
                padding: 4, borderRadius: 4,
              }}
            >
              {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: '100%', justifyContent: 'center', padding: '11px 0', marginTop: 8 }}
            disabled={loading}
          >
            {loading
              ? <><div className="spinner" style={{ width: 16, height: 16 }} /> Verificando…</>
              : 'Iniciar sesión'}
          </button>
        </form>

        {/* Pie de página del login */}
        <div style={{
          marginTop: 24,
          textAlign: 'center',
          fontSize: 11,
          color: 'var(--text-muted)',
          lineHeight: 1.6,
        }}>
          ¿Olvidaste tu contraseña?{' '}
          <span style={{ color: 'var(--accent)' }}>Contacta al administrador del sistema</span>
          <br />
          Máx. 5 intentos por 15 minutos
        </div>
      </div>
    </div>
  );
}
