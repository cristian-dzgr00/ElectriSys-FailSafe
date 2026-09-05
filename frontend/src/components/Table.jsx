import { memo } from 'react';
import { SkeletonTable } from './Skeleton';

/**
 * Table — Componente de tabla optimizado con React.memo.
 * Evita re-renders innecesarios en tablas con muchos registros.
 */
const Table = memo(function Table({
  columns,
  data,
  loading,
  emptyText = 'Sin datos',
  emptyIcon = null,
}) {
  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              {columns.map(col => (
                <th key={col.key} style={col.style}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <SkeletonTable rows={6} cols={columns.length} />
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length}>
                  <div className="empty-state">
                    {emptyIcon && <div style={{ fontSize: 32, marginBottom: 8 }}>{emptyIcon}</div>}
                    <p>{emptyText}</p>
                  </div>
                </td>
              </tr>
            ) : (
              data.map((row, i) => (
                <tr key={row.id ?? i}>
                  {columns.map(col => (
                    <td key={col.key}>
                      {col.render ? col.render(row[col.key], row) : row[col.key]}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
});

export default Table;
