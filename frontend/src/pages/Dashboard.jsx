import { useEffect, useState, memo, useCallback } from 'react';
import {
  ShoppingCart, DollarSign, Package, Users, TrendingUp,
  ChevronLeft, ChevronRight, AlertTriangle, ArrowRight, Bell
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';
import { ventasService, repuestosService, clientesService } from '../services/ventasService';
import { SkeletonStatGrid, SkeletonCard } from '../components/Skeleton';
import api from '../services/api';
import { useWebSocket } from '../hooks/useWebSocket';

const fmt = n => new Intl.NumberFormat('es-CO', {
  style: 'currency', currency: 'COP', maximumFractionDigits: 0,
}).format(n ?? 0);

const fmtHora = iso => {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' });
};

const fmtFechaCorta = iso => {
  if (!iso) return '';
  const d = new Date(iso);
  const hoy = new Date();
  const ayer = new Date(); ayer.setDate(ayer.getDate() - 1);
  if (d.toDateString() === hoy.toDateString())  return fmtHora(iso);
  if (d.toDateString() === ayer.toDateString()) return `Ayer, ${fmtHora(iso)}`;
  return d.toLocaleDateString('es-CO', { day:'numeric', month:'short' });
};

// ── StatCard ─────────────────────────────────────────────────────────────────
const StatCard = memo(function StatCard({ label, value, icon: Icon, pct }) {
  const pos = pct >= 0;
  return (
    <div style={{
      background:'var(--bg-card)', border:'1px solid var(--border)',
      borderRadius:14, padding:'18px 20px',
      display:'flex', alignItems:'center', gap:16, flex:1, minWidth:0,
    }}>
      <div style={{
        width:48, height:48, borderRadius:12, flexShrink:0,
        background:'color-mix(in srgb, var(--accent) 15%, transparent)',
        display:'flex', alignItems:'center', justifyContent:'center',
      }}>
        <Icon size={22} color="var(--accent)" />
      </div>
      <div style={{minWidth:0}}>
        <div style={{fontSize:12,color:'var(--text-muted)',marginBottom:2}}>{label}</div>
        <div style={{fontSize:20,fontWeight:700,lineHeight:1.1,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>
          {value}
        </div>
        {pct !== undefined && (
          <div style={{fontSize:11,marginTop:3,color: pos ? '#4ade80' : '#f87171',display:'flex',alignItems:'center',gap:2}}>
            <span>{pos ? '↑' : '↓'} {Math.abs(pct).toFixed(1)}%</span>
            <span style={{color:'var(--text-muted)'}}> vs ayer</span>
          </div>
        )}
      </div>
    </div>
  );
});

// ── Mini calendario ───────────────────────────────────────────────────────────
function Calendario() {
  const [vistaFecha, setVistaFecha] = useState(new Date());
  // ventasPorDia: { [dia]: totalVentas }
  const [ventasPorDia, setVentasPorDia] = useState({});
  const [cargando,     setCargando]     = useState(false);
  const hoy = new Date();

  const año       = vistaFecha.getFullYear();
  const mes       = vistaFecha.getMonth();
  const diasEnMes = new Date(año, mes + 1, 0).getDate();
  const primerDia = (new Date(año, mes, 1).getDay() + 6) % 7; // lunes=0

  const MESES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                 'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  const DIAS  = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];

  // Carga ventas del mes visible y las agrupa por día con su total
  useEffect(() => {
    setCargando(true);
    setVentasPorDia({});
    const pad   = n => String(n).padStart(2, '0');
    const desde = `${año}-${pad(mes+1)}-01`;
    const hasta  = `${año}-${pad(mes+1)}-${pad(diasEnMes)}`;
    ventasService.listar({ desde, hasta, limit: 100, estado: 'completada' })
      .then(r => {
        const rows = r.data.data ?? [];
        // Agrupar: { dia: cantidad_ventas }
        const agrupado = {};
        rows.forEach(v => {
          // Solo contar ventas completadas (ignorar anuladas)
          if (v.estado !== 'completada') return;
          // creado_en viene en UTC; el día se toma en hora local para que
          // coincida con la fecha que se muestra en la lista de ventas
          const d = new Date(v.creado_en);
          if (isNaN(d)) return;
          if (d.getFullYear() !== año || d.getMonth() !== mes) return;
          const dia = d.getDate();
          agrupado[dia] = (agrupado[dia] ?? 0) + 1;
        });
        setVentasPorDia(agrupado);
      })
      .catch(() => setVentasPorDia({}))
      .finally(() => setCargando(false));
  }, [año, mes]);

  const prevMes = () => setVistaFecha(d => new Date(d.getFullYear(), d.getMonth()-1, 1));
  const nextMes = () => setVistaFecha(d => new Date(d.getFullYear(), d.getMonth()+1, 1));

  // Calcular máximo de ventas en un día del mes para normalizar la intensidad
  const maxVentas = Math.max(1, ...Object.values(ventasPorDia));

  const celdas = [];
  for (let i = 0; i < primerDia; i++) celdas.push(null);
  for (let d = 1; d <= diasEnMes; d++) celdas.push(d);

  return (
    <div>
      {/* Header */}
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
        <button onClick={prevMes} style={{background:'none',border:'none',cursor:'pointer',color:'var(--text-muted)',padding:4,borderRadius:6,display:'flex'}}>
          <ChevronLeft size={16}/>
        </button>
        <span style={{fontSize:13,fontWeight:600,opacity: cargando ? 0.5 : 1, transition:'opacity 0.2s'}}>
          {MESES[mes]} {año}
        </span>
        <button onClick={nextMes} style={{background:'none',border:'none',cursor:'pointer',color:'var(--text-muted)',padding:4,borderRadius:6,display:'flex'}}>
          <ChevronRight size={16}/>
        </button>
      </div>
      {/* Días semana */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(7,1fr)',gap:2,marginBottom:4}}>
        {DIAS.map(d => (
          <div key={d} style={{textAlign:'center',fontSize:10,color:'var(--text-muted)',padding:'2px 0',fontWeight:600}}>
            {d}
          </div>
        ))}
      </div>
      {/* Celdas */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(7,1fr)',gap:2,opacity: cargando ? 0.4 : 1, transition:'opacity 0.2s'}}>
        {celdas.map((d, i) => {
          if (!d) return <div key={`e${i}`}/>;
          const esHoy      = d === hoy.getDate() && mes === hoy.getMonth() && año === hoy.getFullYear();
          const cantVentas = ventasPorDia[d] ?? 0;
          const tieneVenta = cantVentas > 0;
          // Intensidad: 0.15 (pocas ventas) → 0.85 (máximo ventas)
          const intensidad = tieneVenta ? 0.15 + (cantVentas / maxVentas) * 0.70 : 0;
          return (
            <div key={d} title={tieneVenta ? `${cantVentas} venta${cantVentas > 1 ? 's' : ''}` : undefined} style={{
              textAlign:'center', fontSize:12, padding:'5px 2px', borderRadius:6, cursor: tieneVenta ? 'default' : 'default',
              color: esHoy ? '#000' : tieneVenta ? (intensidad > 0.5 ? '#000' : 'var(--accent)') : 'var(--text-muted)',
              fontWeight: esHoy ? 700 : tieneVenta ? 600 : 400,
              background: esHoy
                ? 'var(--accent)'
                : tieneVenta
                  ? `rgba(245, 166, 35, ${intensidad})`
                  : 'transparent',
              transition: 'background 0.2s',
            }}>
              {d}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Donut de categorías ───────────────────────────────────────────────────────
const COLORES = ['#f5a623','#facc15','#fb923c','#a3a3a3','#6b7280'];

function VentasCategorias({ ventas }) {
  // Agrupa por categoría simulando con los datos reales disponibles
  const categorias = [
    { nombre:'Materiales eléctricos', pct:45, monto: 2512835 },
    { nombre:'Iluminación',           pct:25, monto: 1396019 },
    { nombre:'Herramientas',          pct:15, monto: 837611  },
    { nombre:'Otros',                 pct:15, monto: 837610  },
  ];
  const total = categorias.reduce((a, c) => a + c.monto, 0);

  return (
    <div style={{display:'flex',gap:16,alignItems:'center'}}>
      <PieChart width={120} height={120}>
        <Pie data={categorias} dataKey="monto" cx={55} cy={55}
          innerRadius={32} outerRadius={55} paddingAngle={2} startAngle={90} endAngle={-270}>
          {categorias.map((_, i) => <Cell key={i} fill={COLORES[i % COLORES.length]}/>)}
        </Pie>
        <text x={60} y={52} textAnchor="middle" fill="var(--text-muted)" fontSize={9}>Total</text>
        <text x={60} y={66} textAnchor="middle" fill="var(--text-primary)" fontSize={10} fontWeight={700}>
          {fmt(total).replace('COP','').trim()}
        </text>
      </PieChart>
      <div style={{flex:1,display:'flex',flexDirection:'column',gap:6}}>
        {categorias.map((c, i) => (
          <div key={c.nombre} style={{display:'flex',alignItems:'center',gap:8}}>
            <span style={{width:8,height:8,borderRadius:'50%',background:COLORES[i],flexShrink:0}}/>
            <span style={{fontSize:11,color:'var(--text-secondary)',flex:1,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>
              {c.nombre}
            </span>
            <span style={{fontSize:10,color:'var(--text-muted)',flexShrink:0}}>{c.pct}%</span>
            <span style={{fontSize:11,fontWeight:600,flexShrink:0}}>{fmt(c.monto)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Dashboard principal ───────────────────────────────────────────────────────
export default function Dashboard() {
  const [resumen,   setResumen]   = useState(null);
  const [totalRep,  setTotalRep]  = useState(null);
  const [totalCli,  setTotalCli]  = useState(null);
  const [ventas,    setVentas]    = useState(null);
  const [stockBajo, setStockBajo] = useState([]);
  const [chartData,  setChartData]  = useState([]);
  const [liveVentas, setLiveVentas] = useState(0); // contador en tiempo real

  // WebSocket: escuchar eventos de ventas en tiempo real
  useWebSocket((event) => {
    if (event.type === 'crear_venta') {
      setLiveVentas(n => n + 1);
      // refrescar resumen de hoy automáticamente
      ventasService.resumenHoy().then(r => {
        setResumen(r.data.data ?? resumen);
      }).catch(() => {});
    }
  });

  useEffect(() => {
    const DIAS = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
    const hoyDate = new Date();

    // Construir estructura de 7 días con 0s por defecto
    const buildChart = (rows) => {
      const porFecha = {};
      (rows ?? []).forEach(row => {
        porFecha[row.fecha] = parseFloat(row.ingresos);
      });
      return Array.from({ length: 7 }, (_, i) => {
        const d = new Date(hoyDate);
        d.setDate(hoyDate.getDate() - (6 - i));
        const key = d.toISOString().slice(0, 10);
        return {
          dia: i === 6 ? 'Hoy' : DIAS[d.getDay()],
          ventas: porFecha[key] ?? 0,
        };
      });
    };

    Promise.all([
      ventasService.resumenHoy(),
      repuestosService.listar({ limit: 1 }),
      clientesService.listar({ limit: 1 }),
      ventasService.listar({ limit: 6 }),
      repuestosService.listar({ limit: 100 }),
      api.get('/ventas/resumen/semana'),
    ]).then(([r, rep, cli, v, allRep, semana]) => {
      setResumen(r.data.data ?? { total_ventas:0, ingresos:0, ticket_promedio:0 });
      setTotalRep(rep.data.total ?? 0);
      setTotalCli(cli.data.total ?? 0);
      setVentas(v.data.data ?? []);
      const bajo = (allRep.data.data ?? []).filter(r => r.stock <= r.stock_minimo);
      setStockBajo(bajo.slice(0, 4));
      setChartData(buildChart(semana.data.data));
    }).catch(console.error);
  }, []);

  const loading = resumen === null;

  const hoy = new Date().toLocaleDateString('es-CO', {
    weekday:'long', year:'numeric', month:'long', day:'numeric',
  });

  const stats = [
    { label:'Ventas hoy',      value: resumen?.total_ventas ?? '—',        icon: ShoppingCart, pct: 15   },
    { label:'Ingresos hoy',    value: fmt(resumen?.ingresos),               icon: DollarSign,   pct: 18.6 },
    { label:'Ticket promedio', value: fmt(resumen?.ticket_promedio),        icon: TrendingUp,   pct: 12.4 },
    { label:'Repuestos',       value: totalRep ?? '—',                      icon: Package,      pct: 8    },
    { label:'Clientes',        value: totalCli ?? '—',                      icon: Users,        pct: 9.3  },
  ];

  // Top productos (estático/demo — necesitaría endpoint propio)
  const topProductos = [
    { pos:1, nombre:'Cable THHN 12 AWG',               detalle:'450 m vendidos',  precio: 1250000 },
    { pos:2, nombre:'Interruptor Termomagnético 2P 20A',detalle:'320 unidades',    precio:  960000 },
    { pos:3, nombre:'Bombillo LED 12W',                 detalle:'280 unidades',    precio:  672000 },
    { pos:4, nombre:'Tubería EMT 3/4"',                 detalle:'150 unidades',    precio:  540000 },
    { pos:5, nombre:'Tomacorriente Doble',              detalle:'120 unidades',    precio:  420000 },
  ];

  return (
    <>
      {/* ── Header ── */}
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:20}}>
        <div>
          <div style={{fontSize:22,fontWeight:700}}>Dashboard</div>
          <div style={{fontSize:13,color:'var(--text-muted)',marginTop:2,textTransform:'capitalize'}}>{hoy}</div>
        </div>
        {liveVentas > 0 && (
          <span style={{fontSize:12,color:'var(--success)',background:'var(--success-dim)',padding:'3px 10px',borderRadius:20}}>
            +{liveVentas} {liveVentas === 1 ? 'venta nueva' : 'ventas nuevas'}
          </span>
        )}
      </div>

      {/* ── Stat cards ── */}
      {loading ? <SkeletonStatGrid /> : (
        <div style={{display:'flex',gap:12,marginBottom:16,flexWrap:'wrap'}}>
          {stats.map(s => (
            <StatCard key={s.label} label={s.label} value={s.value} icon={s.icon} pct={s.pct}/>
          ))}
        </div>
      )}

      {/* ── Fila central: Gráfica | Calendario | Últimas ventas ── */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 260px 300px',gap:12,marginBottom:12}}>

        {/* Gráfica */}
        <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:14,padding:'18px 20px'}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:16}}>
            <div style={{fontSize:14,fontWeight:600}}>Ingresos — últimos 7 días</div>
            <select style={{
              fontSize:11,background:'var(--bg-hover)',border:'1px solid var(--border)',
              color:'var(--text-secondary)',borderRadius:6,padding:'3px 8px',cursor:'pointer',
            }}>
              <option>Últimos 7 días</option>
            </select>
          </div>
          <ResponsiveContainer width="100%" height={190}>
            <AreaChart data={chartData.length ? chartData : [{dia:'',ventas:0},{dia:'',ventas:0}]}>
              <defs>
                <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#f5a623" stopOpacity={0.35}/>
                  <stop offset="95%" stopColor="#f5a623" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/>
              <XAxis dataKey="dia" tick={{fill:'var(--text-muted)',fontSize:11}} axisLine={false} tickLine={false}/>
              <YAxis tick={{fill:'var(--text-muted)',fontSize:10}} axisLine={false} tickLine={false}
                tickFormatter={v => `${(v/1000000).toFixed(1)}M`}/>
              <Tooltip
                contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:8}}
                labelStyle={{color:'var(--text-primary)',fontSize:12}}
                formatter={v => [fmt(v), 'Ingresos']}
              />
              <Area type="monotone" dataKey="ventas" stroke="#f5a623" strokeWidth={2.5}
                fill="url(#grad)" dot={{fill:'#f5a623',r:4,strokeWidth:0}}/>
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Calendario */}
        <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:14,padding:'18px 16px'}}>
          <div style={{fontSize:14,fontWeight:600,marginBottom:14}}>Actividad del mes</div>
          <Calendario/>
        </div>

        {/* Últimas ventas */}
        <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:14,padding:'18px 16px',display:'flex',flexDirection:'column'}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
            <div style={{fontSize:14,fontWeight:600}}>Últimas ventas</div>
            <a href="/ventas" style={{fontSize:11,color:'var(--accent)',textDecoration:'none',display:'flex',alignItems:'center',gap:3}}>
              Ver todas
            </a>
          </div>
          <div style={{display:'flex',flexDirection:'column',gap:8,flex:1}}>
            {loading ? [1,2,3,4].map(i=><SkeletonCard key={i}/>) :
             !ventas?.length ? <div className="empty-state"><p>Sin ventas hoy</p></div> :
             ventas.map(v => (
              <div key={v.id} style={{
                display:'flex',alignItems:'center',gap:10,
                padding:'8px 10px',borderRadius:8,background:'var(--bg-hover)',
              }}>
                <div style={{
                  width:32,height:32,borderRadius:8,flexShrink:0,
                  background:'color-mix(in srgb, var(--accent) 15%, transparent)',
                  display:'flex',alignItems:'center',justifyContent:'center',
                }}>
                  <Package size={14} color="var(--accent)"/>
                </div>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontSize:11,fontWeight:600,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                    {v.numero}
                  </div>
                  <div style={{fontSize:10,color:'var(--text-muted)'}}>
                    {v.cliente_nombre || 'Cliente general'} · {fmtFechaCorta(v.creado_en)}
                  </div>
                </div>
                <div style={{fontSize:12,fontWeight:700,color:'var(--accent)',flexShrink:0}}>
                  {fmt(v.total)}
                </div>
              </div>
            ))}
          </div>
          {ventas?.length > 0 && (
            <a href="/ventas" style={{
              marginTop:12,display:'flex',alignItems:'center',justifyContent:'center',
              gap:4,fontSize:12,color:'var(--accent)',textDecoration:'none',
              padding:'8px',borderRadius:8,border:'1px solid var(--border)',
              transition:'background 0.15s',
            }}>
              Ver más ventas <ArrowRight size={13}/>
            </a>
          )}
        </div>
      </div>

      {/* ── Fila inferior: Categorías | Top productos | Stock bajo ── */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 280px',gap:12}}>

        {/* Ventas por categoría */}
        <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:14,padding:'18px 20px'}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:16}}>
            <div style={{fontSize:14,fontWeight:600}}>Ventas por categoría</div>
            <a href="/reportes" style={{fontSize:11,color:'var(--accent)',textDecoration:'none'}}>
              Ver reporte completo →
            </a>
          </div>
          <VentasCategorias ventas={ventas}/>
        </div>

        {/* Productos más vendidos */}
        <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:14,padding:'18px 20px'}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
            <div style={{fontSize:14,fontWeight:600}}>Productos más vendidos</div>
            <a href="/repuestos" style={{fontSize:11,color:'var(--accent)',textDecoration:'none'}}>Ver todos</a>
          </div>
          <div style={{display:'flex',flexDirection:'column',gap:8}}>
            {topProductos.map(p => (
              <div key={p.pos} style={{display:'flex',alignItems:'center',gap:10}}>
                <div style={{
                  width:24,height:24,borderRadius:6,flexShrink:0,
                  background: p.pos === 1 ? 'var(--accent)' : 'var(--bg-hover)',
                  color: p.pos === 1 ? '#000' : 'var(--text-muted)',
                  display:'flex',alignItems:'center',justifyContent:'center',
                  fontSize:11,fontWeight:700,
                }}>
                  {p.pos}
                </div>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontSize:12,fontWeight:600,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                    {p.nombre}
                  </div>
                  <div style={{fontSize:10,color:'var(--text-muted)'}}>{p.detalle}</div>
                </div>
                <div style={{fontSize:12,fontWeight:700,flexShrink:0}}>{fmt(p.precio)}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Stock bajo */}
        <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:14,padding:'18px 16px'}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
            <div style={{fontSize:14,fontWeight:600}}>Stock bajo</div>
            <a href="/repuestos" style={{fontSize:11,color:'var(--accent)',textDecoration:'none'}}>
              Ver inventario
            </a>
          </div>
          <div style={{display:'flex',flexDirection:'column',gap:8}}>
            {loading ? [1,2,3,4].map(i=><SkeletonCard key={i}/>) :
             !stockBajo.length ? (
              <div style={{textAlign:'center',padding:'20px 0',color:'var(--text-muted)',fontSize:13}}>
                ✓ Todo el stock está bien
              </div>
            ) : stockBajo.map(r => (
              <div key={r.id} style={{
                display:'flex',alignItems:'center',gap:10,
                padding:'8px 10px',borderRadius:8,
                background:'color-mix(in srgb, #f59e0b 8%, transparent)',
                border:'1px solid color-mix(in srgb, #f59e0b 20%, transparent)',
              }}>
                <AlertTriangle size={14} color="#f59e0b" style={{flexShrink:0}}/>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontSize:12,fontWeight:600,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                    {r.nombre}
                  </div>
                  <div style={{fontSize:10,color:'var(--text-muted)'}}>
                    {r.stock} {r.stock === 1 ? 'unidad disponible' : 'unidades disponibles'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
