import { useEffect, useState, useRef } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area, PieChart, Pie, Cell, Legend
} from 'recharts';
import { ventasService, repuestosService } from '../services/ventasService';
import { useToastContext } from '../context/ToastContext';
import { SkeletonCard, SkeletonText } from '../components/Skeleton';
import { Tooltip as TT } from '../components/Tooltip';
import { Filter, FileText, Calendar, TrendingUp, DollarSign, ShoppingCart, Package, HelpCircle, Download } from 'lucide-react';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';

const fmt = n => new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(n);
const COLORS = ['#f5a623','#e07b39','#4caf7d','#3b8bd4','#e05252','#9c6bae','#f0c040'];
const METODO_LABEL = { efectivo:'Efectivo', tarjeta:'Tarjeta', transferencia:'Transferencia', credito:'Crédito' };

function KpiCard({ icon: Icon, label, value, color, desc }) {
  return (
    <div style={{
      background:'var(--bg-card)', border:'1px solid var(--border)',
      borderRadius:'var(--radius-lg)', padding:'18px 20px',
      display:'flex', alignItems:'center', gap:14,
      transition:'border-color var(--transition), transform var(--transition)',
    }}
    onMouseEnter={e=>{e.currentTarget.style.borderColor=color||'var(--accent)';e.currentTarget.style.transform='translateY(-1px)';}}
    onMouseLeave={e=>{e.currentTarget.style.borderColor='var(--border)';e.currentTarget.style.transform='translateY(0)';}}>
      <div style={{width:42,height:42,borderRadius:10,background:`${color}22`||'var(--accent-dim)',display:'flex',alignItems:'center',justifyContent:'center',color:color||'var(--accent)',flexShrink:0}}>
        <Icon size={20}/>
      </div>
      <div style={{flex:1}}>
        <div style={{display:'flex',alignItems:'center',gap:5}}>
          <div style={{fontSize:11,color:'var(--text-secondary)',textTransform:'uppercase',letterSpacing:'.05em',marginBottom:3}}>{label}</div>
          {desc && <TT text={desc}><HelpCircle size={11} color="var(--text-muted)" style={{cursor:'help',flexShrink:0}}/></TT>}
        </div>
        <div style={{fontSize:20,fontWeight:700,color:'var(--text-primary)'}}>{value}</div>
      </div>
    </div>
  );
}

function SectionCard({ title, icon, children }) {
  return (
    <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:'var(--radius-lg)',padding:'20px'}}>
      <div style={{display:'flex',alignItems:'center',gap:8,fontSize:11,fontWeight:700,color:'var(--accent)',textTransform:'uppercase',letterSpacing:'.07em',marginBottom:16}}>
        <span style={{fontSize:14}}>{icon}</span> {title}
      </div>
      {children}
    </div>
  );
}

const today    = new Date().toISOString().split('T')[0];
const monthAgo = new Date(Date.now()-30*24*60*60*1000).toISOString().split('T')[0];

export default function Reportes() {
  const toast = useToastContext();
  const [ventas,      setVentas]      = useState([]);
  const [repuestos,   setRepuestos]   = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [desde,       setDesde]       = useState(monthAgo);
  const [hasta,       setHasta]       = useState(today);
  const [filtradas,   setFiltradas]   = useState([]);
  const [exportando,  setExportando]  = useState(false);
  const reportRef = useRef(null);
  const chartsRef = useRef(null);
  const chart1Ref = useRef(null);
  const chart2Ref = useRef(null);
  const chart3Ref = useRef(null);
  const chart4Ref = useRef(null);

  const exportarPDF = async () => {
    setExportando(true);
    toast('Generando PDF, espera un momento…', { type: 'info' });
    try {
      const pdf    = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
      const pageW  = pdf.internal.pageSize.getWidth();
      const pageH  = pdf.internal.pageSize.getHeight();
      const M      = 14;
      const usableW= pageW - M * 2;
      const GOLD   = [245, 166, 35];
      const DARK   = [17,  17,  17];
      const GRAY   = [120, 120, 120];
      const fmtNum = n => new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(n);
      const fmtFecha = s => s ? s.split('T')[0].split('-').reverse().join('/') : '—';

      const addPageHeader = (pg) => {
        pdf.setFillColor(...GOLD);
        pdf.rect(0, 0, pageW, 18, 'F');
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(13);
        pdf.setTextColor(...DARK);
        pdf.text('ElectriSys POS System', M, 8);
        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(9);
        pdf.text('Reporte de Ventas e Inventario', M, 13.5);
        pdf.setFontSize(8);
        pdf.text(`Periodo: ${fmtFecha(desde+'T')} al ${fmtFecha(hasta+'T')}`, pageW - M, 8, { align: 'right' });
        pdf.text(`Generado: ${new Date().toLocaleString('es-CO')}`, pageW - M, 13.5, { align: 'right' });
        pdf.setFontSize(7.5);
        pdf.setTextColor(...GRAY);
        pdf.text(`ElectriSys POS  |  Página ${pg}`, M, pageH - 6);
        pdf.text('Reporte generado automáticamente', pageW - M, pageH - 6, { align: 'right' });
        pdf.setDrawColor(...GOLD);
        pdf.setLineWidth(0.4);
        pdf.line(M, pageH - 9, pageW - M, pageH - 9);
      };

      const sectionTitle = (text, y) => {
        pdf.setFillColor(30, 30, 30);
        pdf.rect(M, y, usableW, 8, 'F');
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(9);
        pdf.setTextColor(...GOLD);
        pdf.text(text, M + 3, y + 5.5);
        return y + 11;
      };

      const drawTable = (headers, rows, colWidths, y) => {
        const rowH = 7;
        pdf.setFillColor(...GOLD);
        pdf.rect(M, y, usableW, rowH, 'F');
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(8);
        pdf.setTextColor(...DARK);
        let x = M;
        headers.forEach((h, i) => { pdf.text(h, x + 2, y + 5); x += colWidths[i]; });
        y += rowH;
        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(8);
        rows.forEach((row, ri) => {
          if (ri % 2 === 0) { pdf.setFillColor(28, 28, 28); pdf.rect(M, y, usableW, rowH, 'F'); }
          pdf.setTextColor(220, 220, 220);
          x = M;
          row.forEach((cell, ci) => { pdf.text(String(cell ?? '—'), x + 2, y + 5); x += colWidths[ci]; });
          pdf.setDrawColor(45, 45, 45);
          pdf.setLineWidth(0.1);
          pdf.line(M, y + rowH, M + usableW, y + rowH);
          y += rowH;
        });
        return y + 3;
      };

      // PÁGINA 1
      pdf.setFillColor(18, 18, 18);
      pdf.rect(0, 0, pageW, pageH, 'F');
      addPageHeader(1);
      let y = 26;

      y = sectionTitle('Resumen general', y);
      y = drawTable(
        ['Indicador', 'Valor'],
        [
          ['Total de ventas', String(totalVentas)],
          ['Ingresos totales', fmtNum(totalIngresos)],
          ['Ticket promedio', fmtNum(ticketPromedio)],
          ['Valor inventario', fmtNum(valorInventario)],
          ['Productos en alerta', String(stockCritico)],
        ],
        [110, 72], y
      );

      y += 4;
      y = sectionTitle('Ventas por d\u00eda', y);
      const vpd = (() => {
        const map = {};
        filtradas.forEach(v => {
          const dia = (v.creado_en || '').split('T')[0].split(' ')[0];
          if (!dia) return;
          if (!map[dia]) map[dia] = { count: 0, total: 0 };
          map[dia].count++;
          map[dia].total += parseFloat(v.total || 0);
        });
        return Object.entries(map)
          .sort(([a],[b]) => b.localeCompare(a))
          .map(([fecha, d]) => [fmtFecha(fecha+'T'), String(d.count), fmtNum(d.total)]);
      })();
      y = drawTable(
        ['Fecha', '# Ventas', 'Total del d\u00eda'],
        vpd.length ? vpd : [['Sin datos en el per\u00edodo', '', '']],
        [70, 50, 62], y
      );

      y += 4;
      y = sectionTitle('Productos con stock bajo', y);
      const stockRows = repuestos
        .filter(r => r.stock <= r.stock_minimo)
        .slice(0, 10)
        .map(r => [r.codigo||'—', (r.nombre||'').slice(0,32), (r.categoria||'—'), String(r.stock), String(r.stock_minimo)]);
      y = drawTable(
        ['C\u00f3digo', 'Descripci\u00f3n', 'Categor\u00eda', 'Stock', 'M\u00ednimo'],
        stockRows.length ? stockRows : [['Sin productos en alerta','','','','']],
        [22, 74, 42, 18, 26], y
      );

      // PÁGINA 2 — Gráficas
      pdf.addPage();
      pdf.setFillColor(18, 18, 18);
      pdf.rect(0, 0, pageW, pageH, 'F');
      addPageHeader(2);
      y = 26;
      y = sectionTitle('Gr\u00e1ficas del per\u00edodo', y);

      const chartRefs = [chart1Ref, chart2Ref, chart3Ref, chart4Ref];
      const labels = ['INGRESOS POR DÍA','TOP 5 PRODUCTOS MÁS VENDIDOS','ACUMULADO DE INGRESOS','DISTRIBUCIÓN POR MÉTODO DE PAGO'];
      const gW = (usableW / 2) - 2;
      const gH = 62;

      for (let idx = 0; idx < 4; idx++) {
        const ref = chartRefs[idx];
        if (!ref.current) continue;
        const canvas = await html2canvas(ref.current, {
          scale: 2, useCORS: true, backgroundColor: '#1a1a1a',
          scrollY: -window.scrollY,
        });
        const r = Math.floor(idx / 2);
        const c = idx % 2;
        const xPos = M + c * (gW + 4);
        const yPos = y + r * (gH + 12);
        pdf.setDrawColor(...GOLD);
        pdf.setLineWidth(0.3);
        pdf.setFillColor(22, 22, 22);
        pdf.roundedRect(xPos, yPos, gW, gH + 8, 2, 2, 'FD');
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(6.5);
        pdf.setTextColor(...GOLD);
        pdf.text(labels[idx], xPos + 3, yPos + 5);
        pdf.addImage(canvas.toDataURL('image/png'), 'PNG', xPos + 1, yPos + 7, gW - 2, gH);
      }

      pdf.save(`reporte-electrisys-${desde}-al-${hasta}.pdf`);
      toast('PDF descargado correctamente', { type: 'success' });
    } catch (err) {
      console.error(err);
      toast('Error al generar el PDF', { type: 'error' });
    } finally {
      setExportando(false);
    }
  };


  useEffect(() => {
    Promise.all([ventasService.listar({ limit: 500 }), repuestosService.listar({ limit: 500 })])
      .then(([v, r]) => {
        setVentas(v.data.data ?? []);
        setRepuestos(r.data.data ?? []);
      })
      .catch(() => toast('Error cargando datos de reportes', { type:'error' }))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { aplicarFiltro(); }, [ventas, desde, hasta]);

  const aplicarFiltro = () => {
    const d = new Date(desde + 'T00:00:00');
    const h = new Date(hasta  + 'T23:59:59');
    setFiltradas(ventas.filter(v => {
      const f = new Date(v.creado_en);
      return f >= d && f <= h && v.estado === 'completada';
    }));
  };

  const ingresosPorDia = () => {
    const map = {};
    filtradas.forEach(v => {
      const dia = (v.creado_en || '').split('T')[0].split(' ')[0]; if (!dia) return;
      map[dia] = (map[dia] || 0) + parseFloat(v.total);
    });
    return Object.entries(map).sort(([a],[b])=>a.localeCompare(b))
      .map(([fecha,total]) => ({ fecha: fecha.slice(5).replace('-','/'), total }));
  };

  const acumulado = () => {
    let acc = 0;
    return ingresosPorDia().map(d => { acc += d.total; return { fecha: d.fecha, acumulado: acc }; });
  };

  const metodosPago = () => {
    const map = {};
    filtradas.forEach(v => {
      const m = METODO_LABEL[v.metodo_pago] || v.metodo_pago;
      map[m] = (map[m] || 0) + parseFloat(v.total);
    });
    return Object.entries(map).map(([name, value]) => ({ name, value }));
  };

  const topProductos = repuestos.slice()
    .sort((a,b) => (b.stock_minimo - b.stock) - (a.stock_minimo - a.stock))
    .slice(0,5)
    .map(r => ({ codigo: r.codigo||'—', nombre: r.nombre, stock: r.stock, stock_minimo: r.stock_minimo }));

  const topDona = topProductos.map((r,i) => ({ name: r.codigo||r.nombre.slice(0,8), value: Math.max(1,10-i*2) }));

  const totalIngresos  = filtradas.reduce((s,v) => s + parseFloat(v.total||0), 0);
  const totalVentas    = filtradas.length;
  const ticketPromedio = totalVentas ? totalIngresos / totalVentas : 0;
  const stockCritico   = repuestos.filter(r => r.stock <= r.stock_minimo).length;
  const valorInventario= repuestos.reduce((s,r) => s + parseFloat(r.precio_venta||0) * r.stock, 0);

  const diasLabel = `${desde.split('-').reverse().join('/')} — ${hasta.split('-').reverse().join('/')}`;

  const barData  = ingresosPorDia();
  const areaData = acumulado();
  const pieData  = metodosPago();

  return (
    <>
      <div style={{marginBottom:24,display:'flex',alignItems:'flex-start',justifyContent:'space-between',flexWrap:'wrap',gap:12}}>
        <div>
          <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:4}}>
            <TrendingUp size={22} color="var(--accent)"/>
            <div className="page-title">Reportes y Estadísticas</div>
          </div>
          <div className="page-subtitle">Analiza ventas por período, métodos de pago e inventario crítico</div>
        </div>
        {!loading && (
          <button
            className="btn btn-primary"
            onClick={exportarPDF}
            disabled={exportando}
            style={{display:'flex',alignItems:'center',gap:7,whiteSpace:'nowrap'}}
          >
            <Download size={14}/>
            {exportando ? 'Generando PDF…' : 'Exportar PDF'}
          </button>
        )}
      </div>

      {/* Filtros */}
      <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:'var(--radius-lg)',padding:'16px 20px',display:'flex',alignItems:'center',gap:16,flexWrap:'wrap',marginBottom:20}}>
        <div>
          <div style={{fontSize:10,color:'var(--text-muted)',textTransform:'uppercase',letterSpacing:'.05em',marginBottom:4}}>DESDE</div>
          <input type="date" className="form-control" value={desde} max={hasta} onChange={e=>setDesde(e.target.value)} style={{width:150}}/>
        </div>
        <div>
          <div style={{fontSize:10,color:'var(--text-muted)',textTransform:'uppercase',letterSpacing:'.05em',marginBottom:4}}>HASTA</div>
          <input type="date" className="form-control" value={hasta} min={desde} max={today} onChange={e=>setHasta(e.target.value)} style={{width:150}}/>
        </div>
        <button className="btn btn-primary" style={{marginTop:16}} onClick={aplicarFiltro}>
          <Filter size={14}/> Aplicar filtros
        </button>
        <div style={{marginTop:16,display:'flex',alignItems:'center',gap:6,background:'var(--bg-hover)',borderRadius:8,padding:'7px 12px',fontSize:12,color:'var(--text-secondary)'}}>
          <Calendar size={13} color="var(--accent)"/>{diasLabel}
        </div>
      </div>

      {loading ? (
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16,marginBottom:16}}>
          {[1,2,3,4].map(i=><div key={i} className="card"><SkeletonText width="60%" mb={12}/><div style={{height:220,borderRadius:6,background:'var(--bg-hover)'}}/>
          </div>)}
        </div>
      ) : (
        <div ref={reportRef}>
          {/* Gráficas */}
          <div ref={chartsRef} style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16,marginBottom:16}}>
            <div ref={chart1Ref}><SectionCard title="Ingresos por día" icon="📊">
              {barData.length===0 ? <div className="empty-state"><p>Sin ventas en el período seleccionado</p></div> : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={barData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2e2e2e"/>
                    <XAxis dataKey="fecha" tick={{fill:'#a0a0a0',fontSize:10}} axisLine={false} tickLine={false}/>
                    <YAxis tick={{fill:'#a0a0a0',fontSize:10}} axisLine={false} tickLine={false} tickFormatter={v=>`$${(v/1000000).toFixed(1)}M`}/>
                    <Tooltip contentStyle={{background:'#1e1e1e',border:'1px solid #2e2e2e',borderRadius:8}} formatter={v=>[fmt(v),'Ingresos']}/>
                    <Bar dataKey="total" fill="#f5a623" radius={[4,4,0,0]}/>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </SectionCard></div>

            <div ref={chart2Ref}><SectionCard title="Top 5 productos" icon="🥧">
              {topDona.length===0 ? <div className="empty-state"><p>Sin datos</p></div> : (
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={topDona} cx="40%" cy="50%" innerRadius={55} outerRadius={90} dataKey="value" paddingAngle={2}>
                      {topDona.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}
                    </Pie>
                    <Legend layout="vertical" align="right" verticalAlign="middle" iconSize={10} formatter={v=><span style={{color:'var(--text-secondary)',fontSize:11}}>{v}</span>}/>
                    <Tooltip contentStyle={{background:'#1e1e1e',border:'1px solid #2e2e2e',borderRadius:8}}/>
                  </PieChart>
                </ResponsiveContainer>
              )}
            </SectionCard></div>

            <div ref={chart3Ref}><SectionCard title="Ingresos acumulados" icon="📈">
              {areaData.length===0 ? <div className="empty-state"><p>Sin ventas en el período seleccionado</p></div> : (
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={areaData}>
                    <defs>
                      <linearGradient id="gradAcc" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#4caf7d" stopOpacity={0.35}/>
                        <stop offset="95%" stopColor="#4caf7d" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2e2e2e"/>
                    <XAxis dataKey="fecha" tick={{fill:'#a0a0a0',fontSize:10}} axisLine={false} tickLine={false}/>
                    <YAxis tick={{fill:'#a0a0a0',fontSize:10}} axisLine={false} tickLine={false} tickFormatter={v=>`$${(v/1000000).toFixed(1)}M`}/>
                    <Tooltip contentStyle={{background:'#1e1e1e',border:'1px solid #2e2e2e',borderRadius:8}} formatter={v=>[fmt(v),'Acumulado']}/>
                    <Area type="monotone" dataKey="acumulado" stroke="#4caf7d" strokeWidth={2} fill="url(#gradAcc)" dot={{fill:'#4caf7d',r:3}}/>
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </SectionCard></div>

            <div ref={chart4Ref}><SectionCard title="Distribución por método de pago" icon="💳">
              {pieData.length===0 ? <div className="empty-state"><p>Sin ventas en el período seleccionado</p></div> : (
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={pieData} cx="40%" cy="50%" outerRadius={90} dataKey="value" paddingAngle={2}>
                      {pieData.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}
                    </Pie>
                    <Legend layout="vertical" align="right" verticalAlign="middle" iconSize={10} formatter={v=><span style={{color:'var(--text-secondary)',fontSize:11}}>{v}</span>}/>
                    <Tooltip contentStyle={{background:'#1e1e1e',border:'1px solid #2e2e2e',borderRadius:8}} formatter={v=>[fmt(v),'Ingresos']}/>
                  </PieChart>
                </ResponsiveContainer>
              )}
            </SectionCard></div>
          </div>

          {/* Tabla top productos */}
          <div style={{marginBottom:16}}>
            <SectionCard title="Estado de inventario — productos críticos" icon="🏆">
              <table style={{width:'100%',borderCollapse:'collapse'}}>
                <thead>
                  <tr style={{background:'var(--accent)',borderRadius:6}}>
                    {['Código','Descripción','Stock actual','Stock mínimo','Estado'].map(h=>(
                      <th key={h} style={{padding:'10px 14px',textAlign:'left',fontSize:12,fontWeight:700,color:'#111'}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {topProductos.map((r,i)=>{
                    const estado = r.stock <= 0 ? 'Sin stock' : r.stock <= r.stock_minimo ? 'Stock bajo' : 'Normal';
                    const badgeClass = r.stock <= 0 ? 'badge-danger' : r.stock <= r.stock_minimo ? 'badge-warning' : 'badge-success';
                    return (
                      <tr key={i} style={{borderBottom:'1px solid var(--border)',background:i%2===0?'var(--bg-hover)':'transparent'}}>
                        <td style={{padding:'10px 14px',fontSize:13}}>{r.codigo}</td>
                        <td style={{padding:'10px 14px',fontSize:13}}>{r.nombre}</td>
                        <td style={{padding:'10px 14px',fontSize:13,textAlign:'center'}}><span className={`badge ${badgeClass}`}>{r.stock}</span></td>
                        <td style={{padding:'10px 14px',fontSize:13,textAlign:'center'}}>{r.stock_minimo}</td>
                        <td style={{padding:'10px 14px',fontSize:13}}><span className={`badge ${badgeClass}`}>{estado}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </SectionCard>
          </div>

          {/* KPIs */}
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:14}}>
            <KpiCard icon={ShoppingCart} label="Ventas en el período"  value={totalVentas}         color="#f5a623" desc="Total de ventas completadas en el rango de fechas seleccionado"/>
            <KpiCard icon={DollarSign}   label="Ingresos totales"      value={fmt(totalIngresos)}  color="#4caf7d" desc="Suma de todas las ventas completadas en el período"/>
            <KpiCard icon={TrendingUp}   label="Ticket promedio"       value={fmt(ticketPromedio)} color="#3b8bd4" desc="Valor promedio por venta = Ingresos totales ÷ Número de ventas"/>
            <KpiCard icon={Package}      label="Valor de inventario"   value={fmt(valorInventario)}color="#9c6bae" desc="Suma del precio de venta × stock de todos los repuestos activos"/>
            <KpiCard icon={FileText}     label="Productos en alerta"   value={stockCritico}        color="#e05252" desc="Repuestos cuyo stock actual está en o por debajo del stock mínimo configurado"/>
          </div>
        </div>
      )}
    </>
  );
}