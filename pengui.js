/* El asistente, anclado en la barra superior.

   Antes flotaba fijo abajo a la izquierda, al lado de la barra lateral, y
   ahí tapaba el contenido: en la portada quedaba justo encima del enlace
   que abre los datos del gráfico. Un elemento flotante siempre va a estar
   encima de algo, así que en vez de correrlo unos píxeles se lo pasó a la
   barra superior, al lado de la campana de alertas, que es donde el
   usuario ya busca las acciones de la pantalla.

   El panel se abre debajo del botón y alineado a la derecha, igual que el
   de alertas: dos cosas que se abren igual se aprenden una sola vez.

   El iframe conserva la consulta al cerrar el panel. */
(() => {
  'use strict';
  if (window.self !== window.top || location.pathname === '/asistente') return;

  const host = document.createElement('div'); host.id = 'pengui';
  const root = host.attachShadow({mode:'open'});

  // Las variables de color atraviesan el shadow DOM, así que el botón sigue
  // al tema claro y al oscuro sin repetir la paleta. Los valores de reserva
  // son para el caso de que el asistente se monte en una pantalla que no
  // las defina.
  root.innerHTML = `<style>
    :host{position:relative;z-index:20;font:13px Inter,system-ui,sans-serif;color:var(--ink,#111)}
    *{box-sizing:border-box}button{font:inherit;cursor:pointer}
    button:focus-visible,a:focus-visible{outline:2px solid var(--orange,#ffd400);outline-offset:2px}
    .launch{position:relative;width:38px;height:38px;display:grid;place-items:center;padding:0;
      border:1px solid var(--line,rgba(0,0,0,.12));border-radius:10px;
      background:var(--panel,#fff);color:inherit;transition:.18s background,.18s border-color}
    .launch:hover,.launch[aria-expanded="true"]{background:var(--panel-2,#f2f2f2);border-color:var(--orange,#ffd400)}
    .launch svg{width:21px;height:25px;transform-origin:50% 90%;transition:.18s transform}
    .launch:hover svg{transform:rotate(-6deg)}
    .jump{animation:saludo .65s ease}
    @keyframes saludo{0%,100%{transform:translateY(0) rotate(0)}25%{transform:translateY(-6px) rotate(-12deg)}
      55%{transform:translateY(-3px) rotate(12deg)}80%{transform:rotate(-6deg)}}
    .chat{position:absolute;right:0;top:calc(100% + 10px);z-index:20;
      width:min(420px,calc(100vw - 32px));height:min(620px,calc(100dvh - 140px));
      display:flex;flex-direction:column;border-radius:12px;overflow:hidden;
      border:1px solid var(--line,rgba(0,0,0,.12));box-shadow:var(--shadow,0 16px 60px rgba(0,0,0,.35));background:#fff}
    [hidden]{display:none!important}
    .head{display:flex;align-items:center;gap:12px;padding:13px 16px;background:#0b0b0b;color:#fff;
      border-bottom:3px solid var(--orange,#ffd400)}
    .head div{flex:1}.head strong{font-size:13px}
    .head small{display:block;margin-top:3px;font-size:11px;color:#cfcfcf}
    .head button,.head a{border:0;background:transparent;color:#fff;padding:7px;border-radius:6px;
      text-decoration:none;font-size:18px;line-height:1}
    iframe{border:0;width:100%;flex:1;min-height:0;background:#f5f5f2}
    /* En pantalla angosta la barra superior deja de ser ancla útil: el panel
       se fija a la ventana, como hace el de alertas. */
    @media(max-width:980px){.chat{position:fixed;right:16px;top:76px;height:min(620px,calc(100dvh - 96px))}}
    @media(prefers-reduced-motion:reduce){.jump{animation:none}.launch:hover svg{transform:none}}
    @media print{:host{display:none}}
  </style>
  <button class="launch" type="button" title="Asistente" aria-label="Abrir el asistente" aria-expanded="false">
    <svg viewBox="0 0 100 120" aria-hidden="true">
      <ellipse cx="33" cy="106" rx="16" ry="7" fill="#ffd400"/><ellipse cx="67" cy="106" rx="16" ry="7" fill="#ffd400"/>
      <path d="M25 51C4 58 7 88 17 83L30 68M75 51C93 40 100 48 86 64L75 73" fill="#242424"/>
      <path d="M20 62C15 13 35 7 50 7S85 13 80 62C93 108 69 111 50 111S7 108 20 62" fill="#0b0b0b"/>
      <ellipse cx="50" cy="76" rx="27" ry="31" fill="#f4f7fa"/>
      <ellipse cx="37" cy="40" rx="17" ry="22" fill="#f4f7fa"/><ellipse cx="63" cy="40" rx="17" ry="22" fill="#f4f7fa"/>
      <ellipse cx="39" cy="39" rx="4" ry="6" fill="#0b0b0b"/><ellipse cx="61" cy="39" rx="4" ry="6" fill="#0b0b0b"/>
      <circle cx="40" cy="37" r="1.5" fill="white"/><circle cx="62" cy="37" r="1.5" fill="white"/>
      <path d="M40 49Q50 43 60 49L50 59Z" fill="#ffd400"/>
      <path d="M24 61Q50 71 76 61L76 70Q50 80 24 70Z" fill="#ffd400"/><path d="M66 70L76 70L77 89L66 85Z" fill="#ffd400"/>
    </svg>
  </button>
  <section class="chat" hidden role="dialog" aria-label="Asistente">
    <div class="head">
      <div><strong>Pengui</strong><small>Asistente · Diemar</small></div>
      <a href="/asistente" aria-label="Abrir el asistente en pantalla completa" title="Pantalla completa">↗</a>
      <button class="close" type="button" aria-label="Cerrar el asistente">×</button>
    </div>
  </section>`;

  const launch = root.querySelector('.launch'),
        chat   = root.querySelector('.chat'),
        close  = root.querySelector('.close');
  let frame;

  function shut(){ chat.hidden = true; launch.setAttribute('aria-expanded','false'); launch.focus(); }

  launch.onclick = () => {
    if (!chat.hidden) { shut(); return; }
    const svg = root.querySelector('svg');
    svg.classList.remove('jump'); void svg.getBoundingClientRect(); svg.classList.add('jump');
    chat.hidden = false; launch.setAttribute('aria-expanded','true');
    if (!frame) {
      frame = document.createElement('iframe');
      frame.title = 'Conversación con Pengui';
      frame.src = '/asistente?embed=1';
      chat.append(frame);
    }
    close.focus();
  };
  close.onclick = shut;

  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !chat.hidden) shut(); });
  window.addEventListener('message', e => {
    if (e.origin === location.origin && frame && e.source === frame.contentWindow && e.data === 'pengui:close') shut();
  });

  // Primero en la barra superior, antes de la campana. Si la pantalla no
  // tiene barra, queda arriba a la derecha por su cuenta en vez de no
  // aparecer: una pantalla sin barra no debería quedarse sin asistente.
  const barra = document.querySelector('.top-actions');
  if (barra) {
    barra.prepend(host);
  } else {
    host.style.cssText = 'position:fixed;top:16px;right:16px;z-index:900';
    document.body.append(host);
  }
})();
