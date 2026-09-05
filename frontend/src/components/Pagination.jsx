import { memo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Pagination — Control de paginación cursor-based.
 */
const Pagination = memo(function Pagination({
  page,
  pageSize,
  total,
  onPrev,
  onNext,
}) {
  const from  = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to    = Math.min(page * pageSize, total);
  const hasPrev = page > 1;
  const hasNext = to < total;

  if (total === 0) return null;

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '12px 16px',
      borderTop: '1px solid var(--border)',
      fontSize: 12, color: 'var(--text-secondary)',
    }}>
      <span>
        Mostrando <strong style={{ color: 'var(--text-primary)' }}>{from}–{to}</strong> de{' '}
        <strong style={{ color: 'var(--text-primary)' }}>{total}</strong> registros
      </span>
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          className="btn btn-ghost btn-sm"
          onClick={onPrev}
          disabled={!hasPrev}
          style={{ padding: '5px 8px', opacity: hasPrev ? 1 : .4 }}
        >
          <ChevronLeft size={14} /> Anterior
        </button>
        <span style={{
          display: 'flex', alignItems: 'center',
          padding: '0 10px', fontWeight: 600,
          color: 'var(--text-primary)', fontSize: 13,
        }}>
          {page}
        </span>
        <button
          className="btn btn-ghost btn-sm"
          onClick={onNext}
          disabled={!hasNext}
          style={{ padding: '5px 8px', opacity: hasNext ? 1 : .4 }}
        >
          Siguiente <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
});

export default Pagination;
