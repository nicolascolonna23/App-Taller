/* Lo de arriba a la derecha, en todas las pantallas: los accesos de
 * administración y la cuenta de uno.
 *
 * Usuarios y Parámetros no son módulos de trabajo: son de quien maneja el
 * sistema, y hasta acá había que volver a la portada para llegar. Este
 * archivo se inyecta en todas las pantallas —como tema.js— y le cuelga
 * los accesos a la barra de arriba, al que los tenga habilitados.
 *
 * Y el nombre de uno pasa a ser un botón: adentro están cambiar la
 * contraseña y cerrar sesión. Antes salir existía en una sola pantalla y
 * cambiarse la contraseña había que pedírselo al que administra.
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
      '.barra-admin a{padding:5px 7px}}' +
      /* El nombre, que ahora se toca. La flechita avisa que hay algo
         adentro: un texto que no parece botón no se toca nunca. */
      '[data-cuenta]{cursor:pointer;position:relative;padding-right:14px}' +
      '[data-cuenta]::after{content:"";position:absolute;right:2px;top:calc(50% - 2px);' +
      'border:4px solid transparent;border-top-color:currentColor;opacity:.6}' +
      '[data-cuenta]:hover::after{opacity:1}' +
      '[data-cuenta] a[href="/salir"]{display:none}' +
      '.menu-cuenta{position:absolute;z-index:1200;min-width:210px;padding:6px;' +
      'border-radius:12px;background:var(--panel,var(--surface-1,#fff));' +
      'color:var(--ink,var(--t,#111));' +
      'border:1px solid var(--hairline-2,var(--l2,rgba(0,0,0,.18)));' +
      'box-shadow:0 18px 40px rgba(0,0,0,.35);font-size:13px}' +
      '.menu-cuenta .quien{padding:9px 10px 7px;line-height:1.4}' +
      '.menu-cuenta .quien b{display:block}' +
      '.menu-cuenta .quien small{opacity:.7}' +
      '.menu-cuenta button,.menu-cuenta a{display:block;width:100%;text-align:left;' +
      'padding:9px 10px;border:0;border-radius:8px;background:none;color:inherit;' +
      'font:inherit;cursor:pointer;text-decoration:none}' +
      '.menu-cuenta button:hover,.menu-cuenta a:hover{background:var(--surface-2,var(--p2,rgba(128,128,128,.14)))}' +
      '.menu-cuenta hr{border:0;border-top:1px solid var(--hairline,var(--l,rgba(128,128,128,.25)));margin:5px 2px}' +
      '.clave-caja{border:0;border-radius:14px;padding:20px;min-width:min(340px,92vw);' +
      'background:var(--panel,var(--surface-1,#fff));color:var(--ink,var(--t,#111));' +
      'box-shadow:0 30px 70px rgba(0,0,0,.45)}' +
      '.clave-caja::backdrop{background:rgba(0,0,0,.45)}' +
      '.clave-caja h3{margin:0 0 6px;font-size:16px}' +
      '.clave-caja p{margin:0 0 14px;font-size:12.5px;opacity:.75;line-height:1.5}' +
      '.clave-caja label{display:block;font-size:12px;margin-bottom:4px}' +
      '.clave-caja input{width:100%;box-sizing:border-box;padding:9px 10px;margin-bottom:12px;' +
      'border-radius:8px;border:1px solid var(--hairline-2,var(--l2,rgba(0,0,0,.25)));' +
      'background:var(--surface-2,var(--p2,#fff));color:inherit;font:inherit}' +
      '.clave-caja .fila{display:flex;gap:8px;justify-content:flex-end;margin-top:4px}' +
      '.clave-caja .fila button{padding:9px 14px;border-radius:8px;font:inherit;cursor:pointer;' +
      'border:1px solid var(--hairline-2,var(--l2,rgba(0,0,0,.25)));background:none;color:inherit}' +
      '.clave-caja .fila button[type=submit]{background:var(--brand,var(--o,#ffd400));' +
      'color:var(--marca-ink,#101419);border-color:transparent;font-weight:700}' +
      '.clave-caja .mal{color:var(--bad,#e35d62);font-size:12.5px;margin:0 0 10px;min-height:16px}';
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

  /* ------------------------------------------------------------------
     LA CUENTA
     ------------------------------------------------------------------
     Cada pantalla escribe el nombre en su propio rincón y algunas lo
     reescriben después de cargar. Por eso no se le cuelga nada adentro:
     se marca el lugar y el clic se escucha desde el documento. Así el
     menú sigue andando aunque la pantalla vuelva a dibujar el nombre. */
  var DONDE_EL_NOMBRE = '#quien, #who, .who, .person, .quien';
  var menu = null;

  function marcarNombre() {
    var caja = document.querySelector(DONDE_EL_NOMBRE);
    if (!caja || caja.dataset.cuenta) return null;
    caja.dataset.cuenta = '1';
    caja.setAttribute('role', 'button');
    caja.setAttribute('tabindex', '0');
    caja.setAttribute('aria-haspopup', 'menu');
    caja.title = 'Tu cuenta';
    return caja;
  }

  function cerrarMenu() {
    if (menu) { menu.remove(); menu = null; }
  }

  function abrirMenu(caja, yo) {
    if (menu) return cerrarMenu();
    var r = caja.getBoundingClientRect();
    menu = document.createElement('div');
    menu.className = 'menu-cuenta';
    menu.setAttribute('role', 'menu');
    menu.innerHTML =
      '<div class="quien"><b></b><small></small></div><hr>' +
      '<button type="button" data-clave>Cambiar contraseña</button>' +
      '<a href="/salir">Cerrar sesión</a>';
    menu.querySelector('b').textContent = yo.nombre || yo.usuario || 'Mi cuenta';
    menu.querySelector('small').textContent =
      [yo.usuario, yo.rol_nombre || yo.rol].filter(Boolean).join(' · ');
    document.body.appendChild(menu);
    /* Pegado al nombre y adentro de la pantalla: en el celular el nombre
       está contra el borde derecho y el menú se salía. */
    var ancho = menu.offsetWidth;
    menu.style.top = (window.scrollY + r.bottom + 8) + 'px';
    menu.style.left = Math.max(8,
      Math.min(window.scrollX + r.right - ancho,
               window.scrollX + document.documentElement.clientWidth - ancho - 8)) + 'px';
    menu.querySelector('[data-clave]').onclick = function () {
      cerrarMenu(); pedirClave();
    };
  }

  /* El cambio de contraseña pide la de ahora: una sesión olvidada en la
     máquina del taller no puede alcanzar para quedarse con la cuenta de
     otro. Al guardarla se cierran todas las sesiones, así que de acá se
     sale al login: es lo que uno espera cuando la cambia porque se la
     vieron. */
  function pedirClave() {
    var caja = document.createElement('dialog');
    caja.className = 'clave-caja';
    caja.innerHTML =
      '<form method="dialog"><h3>Cambiar contraseña</h3>' +
      '<p>Al cambiarla se cierran todas las sesiones abiertas, incluida esta.</p>' +
      '<p class="mal" role="alert"></p>' +
      '<label for="clave-actual">Contraseña de ahora</label>' +
      '<input id="clave-actual" type="password" autocomplete="current-password" required>' +
      '<label for="clave-nueva">Contraseña nueva</label>' +
      '<input id="clave-nueva" type="password" autocomplete="new-password" required minlength="8">' +
      '<label for="clave-repetir">Repetirla</label>' +
      '<input id="clave-repetir" type="password" autocomplete="new-password" required minlength="8">' +
      '<div class="fila"><button type="button" data-cancelar>Cancelar</button>' +
      '<button type="submit">Guardar</button></div></form>';
    document.body.appendChild(caja);
    var mal = caja.querySelector('.mal');
    caja.querySelector('[data-cancelar]').onclick = function () { caja.close(); };
    caja.addEventListener('close', function () { caja.remove(); });
    caja.querySelector('form').addEventListener('submit', function (ev) {
      ev.preventDefault();
      var actual = caja.querySelector('#clave-actual').value;
      var nueva = caja.querySelector('#clave-nueva').value;
      if (nueva !== caja.querySelector('#clave-repetir').value) {
        mal.textContent = 'Las dos nuevas no son iguales.';
        return;
      }
      var boton = caja.querySelector('[type=submit]');
      boton.disabled = true; mal.textContent = '';
      fetch('/api/clave', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actual: actual, nueva: nueva })
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) {
          if (!r.ok) throw new Error(d.error || 'No se pudo cambiar la contraseña.');
          location.href = '/login';
        });
      }).catch(function (e) {
        mal.textContent = e.message; boton.disabled = false;
      });
    });
    if (caja.showModal) caja.showModal();
    caja.querySelector('#clave-actual').focus();
  }

  function cuenta(yo) {
    var caja = marcarNombre();
    if (!caja) return;
    document.addEventListener('click', function (ev) {
      var dentro = ev.target.closest('[data-cuenta]');
      if (dentro) {
        /* El enlace de salir que alguna pantalla ya tenía adentro del
           nombre sigue funcionando: no hay por qué robarle el clic. */
        if (ev.target.closest('a')) return;
        ev.preventDefault();
        return abrirMenu(dentro, yo);
      }
      if (menu && !ev.target.closest('.menu-cuenta')) cerrarMenu();
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') return cerrarMenu();
      if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.closest &&
          ev.target.closest('[data-cuenta]')) {
        ev.preventDefault();
        abrirMenu(ev.target.closest('[data-cuenta]'), yo);
      }
    });
    addEventListener('resize', cerrarMenu);
  }

  function arrancar() {
    fetch('/api/yo', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (yo) { if (yo) { estilo(); poner(yo); cuenta(yo); } })
      .catch(function () { /* sin sesión o sin red: la barra no va */ });
  }

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', arrancar);
  else
    arrancar();
})();
