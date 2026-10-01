/* El asistente, como una tarjeta más de la portada.

   Antes se abría como un panel flotante desde la barra superior, y un
   panel flotante siempre queda encima de algo: tapaba el título y las
   tarjetas del tablero. Ahora ocupa su lugar en la columna de la derecha,
   al lado de los números, y no se superpone con nada.

   Solo existe en la portada: el servidor inyecta este archivo únicamente
   en "/", y acá además se monta solo si la pantalla le dejó el hueco. */
(() => {
  'use strict';
  if (window.self !== window.top) return;
  const hueco = document.getElementById('pengui');
  if (!hueco) return;

  const svg = `<svg viewBox="0 0 100 120" aria-hidden="true">
      <ellipse cx="33" cy="106" rx="16" ry="7" fill="#ffd400"/><ellipse cx="67" cy="106" rx="16" ry="7" fill="#ffd400"/>
      <path d="M25 51C4 58 7 88 17 83L30 68M75 51C93 40 100 48 86 64L75 73" fill="#242424"/>
      <path d="M20 62C15 13 35 7 50 7S85 13 80 62C93 108 69 111 50 111S7 108 20 62" fill="#0b0b0b"/>
      <ellipse cx="50" cy="76" rx="27" ry="31" fill="#f4f7fa"/>
      <ellipse cx="37" cy="40" rx="17" ry="22" fill="#f4f7fa"/><ellipse cx="63" cy="40" rx="17" ry="22" fill="#f4f7fa"/>
      <ellipse cx="39" cy="39" rx="4" ry="6" fill="#0b0b0b"/><ellipse cx="61" cy="39" rx="4" ry="6" fill="#0b0b0b"/>
      <circle cx="40" cy="37" r="1.5" fill="white"/><circle cx="62" cy="37" r="1.5" fill="white"/>
      <path d="M40 49Q50 43 60 49L50 59Z" fill="#ffd400"/>
      <path d="M24 61Q50 71 76 61L76 70Q50 80 24 70Z" fill="#ffd400"/><path d="M66 70L76 70L77 89L66 85Z" fill="#ffd400"/>
    </svg>`;

  hueco.innerHTML = `<div class="pengui-head">
      <span class="pengui-avatar">${svg}</span>
      <span><b>Pengui</b><small>Asistente de IA · solo consulta</small></span>
      <a href="/asistente" title="Pantalla completa" aria-label="Abrir Pengui en pantalla completa">↗</a>
    </div>`;

  const frame = document.createElement('iframe');
  frame.title = 'Conversación con Pengui';
  frame.src = '/asistente?embed=1';
  hueco.append(frame);
  hueco.hidden = false;
})();
