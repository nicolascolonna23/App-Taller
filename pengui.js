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

  /* Titán, el robot de la marca. La imagen está en titan-asistente-avatar.png. */
  const avatar = '<img src="/titan-asistente-avatar.png" alt="" width="36" height="36">';

  hueco.innerHTML = `<div class="pengui-head">
      <span class="pengui-avatar">${avatar}</span>
      <span><b>Titán</b><small>Asistente de IA · solo consulta</small></span>
      <a href="/asistente" title="Pantalla completa" aria-label="Abrir a Titán en pantalla completa">↗</a>
    </div>`;

  const frame = document.createElement('iframe');
  frame.title = 'Conversación con Titán';
  frame.src = '/asistente?embed=1';
  hueco.append(frame);
  hueco.hidden = false;
})();
