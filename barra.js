/* Los accesos de administración, arriba y en todas las pantallas.
 *
 * Usuarios y Parámetros no son módulos de trabajo: son de quien maneja el
 * sistema, y hasta acá había que volver a la portada para llegar. Este
 * archivo se inyecta en todas las pantallas —como tema.js— y le cuelga
 * los accesos a la barra de arriba, al que los tenga habilitados.
 *
 * Lo que se ve acá es comodidad, no seguridad: el permiso lo revisa el
 * servidor en cada pedido (ver permisos.py). Si alguien fuerza el enlace,
 * se choca con la misma puerta cerrada.
 */
(function () {
  'use strict';

  var ACCESOS = [
    { modulo: 'usuarios',   texto: 'Usuarios',   href: '/usuarios' },
    { modulo: 'parametros', texto: 'Parámetros', href: '/parametros' },
  ];

  /* Dónde va: la barra oscura de casi todas las pantallas, o la de la
     portada, que tiene su propia estructura. Si no hay ninguna, no se
     inventa una: la pantalla no la tenía y no es asunto de este archivo. */
  function anclaje() {
    var top = document.querySelector('header.top');
    if (top) return { caja: top, antes: top.querySelector('.who') };
    var barra = document.querySelector('header.topbar .top-actions');
    if (barra) return { caja: barra, antes: barra.querySelector('.person') };
    return null;
  }

  function estilo() {
    if (document.getElementById('barra-admin-css')) return;
    var css = document.createElement('style');
    css.id = 'barra-admin-css';
    /* Hereda el color de la barra en la que cae: la de fondo oscuro y la
       clara de Combustible usan el mismo marcado. */
    css.textContent =
      '.barra-admin{display:inline-flex;align-items:center;gap:6px;' +
      'margin-left:auto;font-size:12px;font-weight:700}' +
      '.barra-admin+.who,.barra-admin+.person{margin-left:14px}' +
      '.barra-admin a{color:inherit;opacity:.65;text-decoration:none;' +
      'display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;padding:7px;border:1px solid currentColor;border-radius:8px;' +
      'white-space:nowrap;line-height:1}' +
      '.barra-admin a:hover,.barra-admin a:focus-visible{opacity:1}' +
      '.barra-admin a.aca{opacity:1}' +
      '@media(max-width:700px){.barra-admin a span{display:none}' +
      '.barra-admin a{padding:5px 7px}}';
    document.head.appendChild(css);
  }

  function icono(modulo) {
    if (modulo === 'usuarios')
      return '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" ' +
        'stroke="currentColor" stroke-width="1.9" aria-hidden="true">' +
        '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/>' +
        '<path d="M17 11.5h4M19 9.5v4"/></svg>';
    return '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" ' +
      'stroke="currentColor" stroke-width="1.9" aria-hidden="true">' +
      '<circle cx="12" cy="12" r="3"/>' +
      '<path d="M12 3v2.5M12 18.5V21M4.2 7.5l2.2 1.3M17.6 15.2l2.2 1.3' +
      'M4.2 16.5l2.2-1.3M17.6 8.8l2.2-1.3"/></svg>';
  }

  function poner(yo) {
    var donde = anclaje();
    if (!donde || document.querySelector('.barra-admin')) return;
    var puede = {};
    (yo.modulos || []).forEach(function (m) { puede[m] = true; });

    var visibles = ACCESOS.filter(function (a) {
      return yo.administra || puede[a.modulo];
    });
    if (!visibles.length) return;

    estilo();
    var caja = document.createElement('nav');
    caja.className = 'barra-admin';
    caja.setAttribute('aria-label', 'Administración');
    caja.innerHTML = visibles.map(function (a) {
      var aca = location.pathname === a.href ? ' aca' : '';
      return '<a class="' + aca.trim() + '" href="' + a.href + '" title="' + a.texto + '" aria-label="' + a.texto + '">' +
             icono(a.modulo) + '</a>';
    }).join('');
    donde.caja.insertBefore(caja, donde.antes);
  }

  function arrancar() {
    fetch('/api/yo', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (yo) { if (yo) poner(yo); })
      .catch(function () { /* sin sesión o sin red: la barra no va */ });
  }

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', arrancar);
  else
    arrancar();
})();
