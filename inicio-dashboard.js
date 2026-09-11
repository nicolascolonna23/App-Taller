/* Dashboard charts consume the same validated aggregates as the headline totals. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = new Intl.NumberFormat('es-AR', {maximumFractionDigits: 1});
  const day = value => String(value).slice(8,10) + '/' + String(value).slice(5,7);
  const month = value => {
    const date = new Date(String(value).slice(0,7) + '-01T12:00:00');
    return Number.isNaN(date.getTime()) ? 'Sin período' : date.toLocaleDateString('es-AR',{month:'short',year:'2-digit'});
  };
  const valid = value => value != null && Number.isFinite(Number(value)) && Number(value) >= 0;
  function kilometros(recorrido, periodo) {
    // A single-day total is contextualized with the last week, not an invented intraday series.
    const ventana = recorrido && recorrido[periodo === 'ayer' ? 'semana' : periodo];
    const serie = ventana?.serie || [];
    el('km-chart-period').textContent = periodo === 'mes' ? 'Últimos 30 días' : 'Últimos 7 días';
    if (!serie.some(p => valid(p.km))) {
      el('km-chart').innerHTML = '<p class="dashboard-empty">Sin lecturas diarias disponibles.</p>';
      el('km-chart-labels').textContent = '';
      el('km-chart-table').textContent = 'Sin datos para el período seleccionado.';
      return;
    }
    const max = Math.max(1, ...serie.filter(p => valid(p.km)).map(p => Number(p.km)));
    el('km-chart').innerHTML = `<div class="chart-scale" aria-hidden="true"><span>${number.format(max)} km</span><span>${number.format(max / 2)}</span><span>0</span></div><div class="daily-columns">${serie.map(p => {
      const label = `${day(p.fecha)} · ${valid(p.km) ? number.format(p.km) + ' km · ' + p.unidades + ' unidades' : 'Sin lecturas'}`;
      const height = valid(p.km) ? Math.max(1, Number(p.km) / max * 100) : 0;
      return `<div class="daily-column ${valid(p.km) ? '' : 'missing'}" tabindex="0" aria-label="${escape(label)}"><div class="daily-bar" style="height:${height}%"></div><span class="chart-tooltip">${escape(label)}</span></div>`;
    }).join('')}</div>`;
    el('km-chart-labels').innerHTML = `<span>${day(serie[0].fecha)}</span><span>${day(serie[Math.floor((serie.length - 1) / 2)].fecha)}</span><span>${day(serie[serie.length - 1].fecha)}</span>`;
    el('km-chart-table').innerHTML = `<table><caption>Kilómetros diarios registrados</caption><thead><tr><th>Fecha</th><th>Distancia</th><th>Unidades</th></tr></thead><tbody>${serie.map(p => `<tr><td>${escape(day(p.fecha))}</td><td>${valid(p.km) ? number.format(p.km) + ' km' : 'Sin lecturas'}</td><td>${number.format(p.unidades || 0)}</td></tr>`).join('')}</tbody></table>`;
  }
  function consumo(data) {
    const rows = [data?.previo, data?.mes].filter(Boolean);
    el('fuel-note').textContent = rows.some(p => p.sin_consumo)
      ? 'Cobertura parcial: los períodos pueden incluir unidades diferentes.'
      : 'Consumo ponderado por distancia · meses cerrados.';
    if (!rows.length || !rows.some(p => valid(p.litros_100km))) {
      el('fuel-chart').innerHTML = '<p class="dashboard-empty">Sin consumo calculado para comparar.</p>';
      return;
    }
    const max = Math.max(1, ...rows.filter(p => valid(p.litros_100km)).map(p => Number(p.litros_100km)));
    el('fuel-chart').innerHTML = rows.map(p => `<div class="fuel-row ${p === data.mes ? 'current' : ''}"><div class="fuel-row-label"><span>${escape(month(p.mes))}${p === data.mes ? ' · último cierre' : ''}</span><strong>${valid(p.litros_100km) ? number.format(p.litros_100km) : '—'}</strong></div><div class="fuel-track"><div style="width:${valid(p.litros_100km) ? Number(p.litros_100km) / max * 100 : 0}%"></div></div>${p.sin_consumo ? `<small>Cobertura parcial: ${number.format(p.sin_consumo)} unidades sin cálculo.</small>` : ''}</div>`).join('');
  }
  function alertas(data) {
    if (!data?.instalado) {
      el('alert-mini-count').textContent = 'Alertas no disponibles';
      el('dashboard-alert-state').textContent = 'No disponible';
      el('dashboard-alert-list').innerHTML = '<p class="dashboard-empty">El módulo de alertas no está configurado.</p>';
      return;
    }
    const resumen = data.resumen || {};
    const total = resumen.total ?? (data.alertas || []).length;
    el('alert-mini-count').textContent = total ? `${number.format(total)} alertas` : 'Sin alertas activas';
    el('alert-mini-priority').textContent = resumen.grave ? `${number.format(resumen.grave)} de prioridad alta` : '';
    el('dashboard-alert-count').textContent = number.format(total);
    el('dashboard-alert-state').textContent = total ? 'alertas activas' : 'Sin alertas activas';
    el('dashboard-alert-critical').hidden = !resumen.grave;
    el('dashboard-alert-critical').textContent = `${number.format(resumen.grave || 0)} de prioridad alta`;
    const meter = el('dashboard-alert-meter');
    meter.hidden = !total;
    meter.innerHTML = ['grave','media','leve'].map((type, index) => `<span class="${type}" style="flex:${Number(resumen[type]) || 0}" title="${['Alta','Media','Baja'][index]}: ${Number(resumen[type]) || 0}"></span>`).join('');
    meter.setAttribute('role','img');
    meter.setAttribute('aria-label',`Prioridad alta: ${resumen.grave || 0}; media: ${resumen.media || 0}; baja: ${resumen.leve || 0}`);
    const rows = (data.alertas || []).slice(0,3);
    el('dashboard-alert-list').innerHTML = rows.length ? rows.map(a => {
      const href = /^\/(?!\/)/.test(a.enlace || '') ? a.enlace : '/alertas';
      const severity = ['grave','media','leve'].includes(a.severidad) ? a.severidad : 'leve';
      return `<a class="dashboard-alert-row" href="${escape(href)}"><span class="severity ${severity}">${({grave:'Alta',media:'Media',leve:'Baja'})[severity]}</span><span><strong>${escape(a.titulo || a.modulo || 'Alerta')}</strong><small>${escape(a.detalle || 'Requiere revisión')}</small></span><span aria-hidden="true">↗</span></a>`;
    }).join('') : '<p class="dashboard-empty">No hay incidencias pendientes de revisión.</p>';
  }
  function alertasError() {
    el('alert-mini-count').textContent = 'Alertas no disponibles';
    el('dashboard-alert-state').textContent = 'No disponible';
    el('dashboard-alert-list').innerHTML = '<p class="dashboard-empty">No se pudieron consultar las alertas. <a href="/alertas">Abrir el módulo</a></p>';
  }
  function error() {
    el('dashboard-status').textContent = 'No se pudo actualizar. Recargue la página para reintentar.';
    el('km-sub').textContent = 'Recorrido no disponible.';
    el('cons-sub').textContent = 'Consumo no disponible.';
    kilometros(null, 'ayer'); consumo(null);
  }
  window.InicioDashboard = {kilometros, consumo, alertas, alertasError, error};
})();
