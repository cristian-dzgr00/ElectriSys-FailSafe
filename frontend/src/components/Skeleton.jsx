/**
 * Skeleton — Componentes de skeleton loader para eliminar el spinner central.
 * Mejora la UX percibida al mostrar la estructura antes que los datos.
 */

const shimmer = {
  background: 'linear-gradient(90deg, var(--bg-hover) 25%, var(--bg-card) 50%, var(--bg-hover) 75%)',
  backgroundSize: '200% 100%',
  animation: 'shimmer 1.4s infinite',
  borderRadius: 6,
};

export function SkeletonRow({ cols = 5 }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} style={{ padding: '12px 14px' }}>
          <div style={{ ...shimmer, height: 14, width: i === 0 ? '60%' : i === cols - 1 ? '40%' : '80%' }} />
        </td>
      ))}
    </tr>
  );
}

export function SkeletonTable({ rows = 6, cols = 5 }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} cols={cols} />
      ))}
    </>
  );
}

export function SkeletonCard({ height = 80 }) {
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: 20,
      display: 'flex', gap: 16, alignItems: 'center',
    }}>
      <div style={{ ...shimmer, width: 44, height: 44, borderRadius: 10, flexShrink: 0 }} />
      <div style={{ flex: 1 }}>
        <div style={{ ...shimmer, height: 11, width: '50%', marginBottom: 8 }} />
        <div style={{ ...shimmer, height: 20, width: '70%' }} />
      </div>
    </div>
  );
}

export function SkeletonText({ width = '100%', height = 14, mb = 0 }) {
  return <div style={{ ...shimmer, width, height, marginBottom: mb, borderRadius: 4 }} />;
}

export function SkeletonStatGrid() {
  return (
    <div className="stat-grid">
      {Array.from({ length: 5 }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
