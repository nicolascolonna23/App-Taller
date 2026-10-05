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

  /* Titán, el robot del asistente: grande, animado y saludando. Las
     animaciones están en sistema.css (.titan-robot). */
  const robot = `<span class="titan-robot entra" style="--alto:128px" role="img"
      aria-label="Titán, el robot asistente, saludando" title="¡Hola! Soy Titán">
      <span class="tr-sombra"></span>
      <span class="tr-flota">
        <img class="tr-cuerpo" src="/titan-robot-cuerpo.png" alt="" width="512" height="628">
        <img class="tr-brazo" src="/titan-robot-brazo.png" alt="" width="512" height="628">
        <span class="tr-ojo izq"></span><span class="tr-ojo der"></span>
      </span>
    </span>`;

  hueco.innerHTML = `<div class="pengui-head titan-cabecera">
      ${robot}
      <div class="titan-globo"><b>Titán</b>Asistente de IA. Consultas sobre flota, stock y vencimientos.<small>Solo consulta · no modifica datos</small></div>
      <a href="/asistente" title="Pantalla completa" aria-label="Abrir a Titán en pantalla completa">↗</a>
    </div>`;

  /* Tocarlo lo hace saludar con más ganas un rato. */
  const muñeco = hueco.querySelector('.titan-robot');
  muñeco.addEventListener('click', () => {
    muñeco.classList.add('saluda');
    clearTimeout(muñeco._t);
    muñeco._t = setTimeout(() => muñeco.classList.remove('saluda'), 2400);
  });

  const frame = document.createElement('iframe');
  frame.title = 'Conversación con Titán';
  frame.src = '/asistente?embed=1';
  hueco.append(frame);
  hueco.hidden = false;
})();
