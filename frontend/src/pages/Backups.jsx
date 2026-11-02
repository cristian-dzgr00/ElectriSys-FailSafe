// frontend/src/pages/Backups.jsx
// Respaldos de la base de datos (Oracle Data Pump).
//
// Es una página aparte y no una sección de Auditoría porque los roles no
// coinciden: Auditoría es solo del dueño, y los respaldos los manejan
// admin y dueño. Ver App.jsx.
//
// El listado se ve sin VPN (con sesión válida); "Respaldar ahora" y la
// descarga del CSV exigen VPN: antes de ejecutarlas se muestra el aviso de
// VpnRequiredModal (ver context/VpnContext.jsx).
//
// El .dmp en sí NO se descarga ni se borra a propósito: contiene la base
// entera (incluidos los hashes de contraseñas), así que sale del servidor
// solo de forma deliberada, nunca por el navegador. Lo que sí se
// puede bajar desde acá es un .zip con un .csv por tabla de negocio (sin
// la columna password ni login_attempts) — ver GET /admin/backups/exportar-csv
// en admin_backup.php. Por eso el nombre del archivo en la tabla es un
// botón: dispara esa exportación, no una descarga del .dmp real.

import { useCallback, useEffect, useState } from 'react';
import { DatabaseBackup, Download, RefreshCw, ShieldCheck, AlertTriangle, Info } from 'lucide-react';
import Table from '../components/Table';
import { useToastContext } from '../context/ToastContext';
import { useVpn } from '../context/VpnContext';
import { backupsService } from '../services/backupsService';

const fmtFechaHora = v => (v ? new Date(v).toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' }) : '—');

export default function Backups() {
  const toast = useToastContext();
  const { exigirVpn, manejarErrorVpn } = useVpn();

  const [data,      setData]      = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [creando,   setCreando]   = useState(false);
  const [exportando, setExportando] = useState(false);
  const [mensaje,   setMensaje]   = useState('');
  const [sinAcceso, setSinAcceso] = useState(false);   // 403: el rol no puede ver los respaldos

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await backupsService.listar();
      setData(r.data.data ?? []);
      setMensaje(r.data.mensaje ?? '');
      setSinAcceso(false);
    } catch (e) {
      if (e.response?.status === 403) setSinAcceso(true);
      else toast('Error cargando los respaldos', { type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const respaldarAhora = async () => {
    if (creando) return;
    if (!exigirVpn()) return;
    setCreando(true);
    try {
      const r = await backupsService.crear();
      toast(r.data.mensaje || 'Respaldo iniciado', { type: 'success' });
      // El .dmp suele estar escrito para cuando la llamada retorna (Data Pump
      // tarda unos segundos en arrancar el job), pero la escritura termina
      // poco después: se recarga con un margen corto y, si aún no aparece,
      // queda el botón "Actualizar".
      setTimeout(load, 3000);
    } catch (e) {
      if (!(await manejarErrorVpn(e))) {
        toast(e.response?.data?.error || 'No se pudo iniciar el respaldo', { type: 'error' });
      }
    } finally {
      setCreando(false);
    }
  };

  // Descarga un .zip con los datos de negocio en CSV (no el .dmp real —
  // ver el comentario del encabezado). "Live": siempre trae los datos
  // actuales, sin importar a qué fila de la tabla pertenezca el botón que
  // se clickeó, porque las filas viejas no tienen un CSV propio guardado.
  const exportarDatos = async () => {
    if (exportando) return;
    if (!exigirVpn()) return;
    setExportando(true);
    try {
      const r = await backupsService.exportarCsv();
      const match = /filename="?([^"]+)"?/.exec(r.headers['content-disposition'] || '');
      const nombre = match?.[1] || 'electrisys_export.zip';
      const url = window.URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = nombre;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      if (!(await manejarErrorVpn(e))) {
        toast('No se pudo generar el archivo de exportación', { type: 'error' });
      }
    } finally {
      setExportando(false);
    }
  };

  const columns = [
    { key: 'archivo', label: 'Archivo', render: v => (
      <button
        onClick={exportarDatos}
        disabled={exportando}
        title="Descarga los datos de negocio en CSV — no es el .dmp real, que nunca sale del servidor por el navegador"
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: 0, background: 'none', border: 'none',
          color: 'var(--accent)', fontWeight: 600, cursor: exportando ? 'default' : 'pointer',
          textDecoration: 'underline',
        }}
      >
        <Download size={13} /> {exportando ? 'Generando…' : v}
      </button>
    )},
    { key: 'fecha',   label: 'Fecha',  render: v => fmtFechaHora(v) },
    { key: 'tamano',  label: 'Tamaño' },
  ];

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Respaldos</div>
          <div className="page-subtitle">
            {sinAcceso ? 'Sin permiso' : `${data.length} respaldo(s) disponibles`}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn btn-ghost" onClick={load} disabled={loading}>
            <RefreshCw size={15} /> Actualizar
          </button>
          <button className="btn btn-primary" onClick={respaldarAhora} disabled={creando || sinAcceso}>
            <DatabaseBackup size={15} /> {creando ? 'Respaldando… (~15 s)' : 'Respaldar ahora'}
          </button>
        </div>
      </div>

      {sinAcceso && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          <AlertTriangle size={15} style={{ verticalAlign: -2, marginRight: 6 }} />
          No tienes permiso para ver los respaldos.
        </div>
      )}

      {!sinAcceso && mensaje && (
        <div className="card" style={{ marginBottom: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
          <Info size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
          {mensaje}
        </div>
      )}

      {!sinAcceso && (
        <>
          <div className="card" style={{ marginBottom: 16, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>
              <ShieldCheck size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
              Cómo funciona
            </div>
            La base de datos es una Oracle Autonomous Database en Oracle Cloud, que hace
            respaldos automáticos y los conserva 60 días (se ven en la consola de Oracle Cloud).
            "Respaldar ahora" crea un respaldo extra con Data Pump (archivos <code>.dmp</code> y{' '}
            <code>.log</code>) en el directorio de respaldos del servidor de la base,{' '}
            <code>ELECTRISYS_BACKUP_DIR</code> — hazlo antes de una operación riesgosa (una
            carga masiva, un cambio de precios en bloque).
            <br />
            Para <strong>restaurar</strong> un respaldo hace falta acceso al administrador de la
            base de datos: no se hace desde esta pantalla porque una restauración reemplaza los
            datos actuales.
            <br />
            Haciendo clic en el nombre del archivo se descarga un <strong>.zip con los datos
            actuales en CSV</strong> (uno por tabla) para revisarlos en Excel — no es el .dmp
            real: ese contiene los hashes de contraseñas y nunca sale del servidor.
          </div>

          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <Table columns={columns} data={data} loading={loading} />
          </div>
        </>
      )}
    </>
  );
}
