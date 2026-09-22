// frontend/src/pages/Backups.jsx
// Respaldos de la base de datos (Oracle Data Pump).
//
// Es una página aparte y no una sección de Auditoría porque los roles no
// coinciden: Auditoría es solo del dueño, y los respaldos los manejan
// admin y dueño. Ver App.jsx.
//
// Acá NO se descargan ni se borran respaldos a propósito: el .dmp contiene
// la base entera (incluidos los hashes de contraseñas), así que sale del
// servidor solo por SSH y de forma deliberada, nunca por el navegador.

import { useCallback, useEffect, useState } from 'react';
import { DatabaseBackup, RefreshCw, ShieldCheck, AlertTriangle } from 'lucide-react';
import Table from '../components/Table';
import { useToastContext } from '../context/ToastContext';
import { backupsService } from '../services/backupsService';

const fmtFechaHora = v => (v ? new Date(v).toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' }) : '—');

export default function Backups() {
  const toast = useToastContext();

  const [data,      setData]      = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [creando,   setCreando]   = useState(false);
  const [accesible, setAccesible] = useState(true);
  const [ruta,      setRuta]      = useState('');
  const [sinAcceso, setSinAcceso] = useState(false);   // 403: fuera de la VPN

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await backupsService.listar();
      setData(r.data.data ?? []);
      setAccesible(r.data.accesible !== false);
      setRuta(r.data.ruta ?? '');
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
      toast(
        e.response?.status === 403
          ? 'Necesitas estar conectado a la VPN para disparar un respaldo'
          : (e.response?.data?.error || 'No se pudo iniciar el respaldo'),
        { type: 'error' },
      );
    } finally {
      setCreando(false);
    }
  };

  const columns = [
    { key: 'archivo', label: 'Archivo' },
    { key: 'fecha',   label: 'Fecha',  render: v => fmtFechaHora(v) },
    { key: 'tamano',  label: 'Tamaño' },
  ];

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Respaldos</div>
          <div className="page-subtitle">
            {sinAcceso ? 'Acceso restringido' : `${data.length} respaldo(s) disponibles`}
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
          Esta sección solo es accesible desde la VPN del negocio. Conéctate a WireGuard
          y vuelve a intentarlo.
        </div>
      )}

      {!sinAcceso && !accesible && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          <AlertTriangle size={15} style={{ verticalAlign: -2, marginRight: 6 }} />
          El volumen de respaldos no está montado en este backend, así que no se pueden
          listar los archivos. El respaldo automático nocturno puede estar funcionando
          igual — revísalo con <code>docker compose logs oracle-backup</code>.
        </div>
      )}

      {!sinAcceso && (
        <>
          <div className="card" style={{ marginBottom: 16, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>
              <ShieldCheck size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
              Cómo funciona
            </div>
            El respaldo automático corre todas las noches a las 2:00 y conserva los últimos
            14 días. "Respaldar ahora" dispara uno extra — hazlo antes de una operación
            riesgosa (una carga masiva, un cambio de precios en bloque).
            {ruta && <> Los archivos quedan en <code>{ruta}</code>, dentro del servidor.</>}
            <br />
            Para <strong>restaurar</strong> un respaldo hace falta entrar por SSH: el
            procedimiento paso a paso está en <code>oracle/backup/restaurar_logico.sh</code>.
            No se hace desde acá porque una restauración reemplaza los datos actuales.
          </div>

          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <Table columns={columns} data={data} loading={loading} />
          </div>
        </>
      )}
    </>
  );
}
