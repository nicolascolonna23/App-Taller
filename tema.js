/* =====================================================================
   CÓMO SE VE LA APLICACIÓN
   ---------------------------------------------------------------------
   Lo carga toda pantalla, arriba de todo. Lee lo que eligió el usuario y
   le pisa los colores a la hoja de estilo de esa pantalla.

   Por qué una traducción y no un solo juego de variables: cada pantalla
   se escribió en su momento con los nombres que le parecieron —una usa
   --bg y otra --plane para lo mismo— y renombrarlas todas de una es
   pedir un error en cada archivo. Acá se dice, una sola vez, qué nombre
   usa cada una para cada cosa, y de ahí en más se piensa en roles: el
   fondo, el panel, el texto, la marca.

   La foto de portada es de cada usuario: sale de la sesión y no de la
   dirección, así nadie ve la del otro.
   ===================================================================== */
(function () {
  'use strict';

  /* El color de cada paleta. Lo demás sale de él. */
  const PALETAS = {
    diemar:'#ff7a1a', azul:'#3d8bfd', verde:'#22a06b',
    violeta:'#8b7bf7', rojo:'#e5484d', grafito:'#8a94a0'
  };

  /* Los dos temas, en roles. El claro no es el oscuro dado vuelta: el
     papel tiene que ser papel y la tinta, tinta. */
  const TEMAS = {
    oscuro: {
      esquema:'dark',
      fondo:'#090b0e', panel:'#12171c', panel2:'#171e24', panel3:'#20262c',
      linea:'rgba(255,255,255,.08)', linea2:'rgba(255,255,255,.14)',
      texto:'#f3f5f6', texto2:'#c5cbd0', apagado:'#9099a4',
      sombra:'0 18px 40px rgba(0,0,0,.45)',
      ok:'#31bd65', atencion:'#f0b429', mal:'#e35d62', dato:'#7db3ef',
      velo:'rgba(9,11,14,.55)', velo2:'rgba(9,11,14,.14)', velo3:'rgba(9,11,14,.90)',
      vidrio:'rgba(15,20,25,.74)', vidrioLinea:'rgba(255,255,255,.14)',
      sombraTexto:'0 2px 12px rgba(0,0,0,.7)'
    },
    claro: {
      esquema:'light',
      fondo:'#f4f6f8', panel:'#ffffff', panel2:'#f0f3f6', panel3:'#e6ebf0',
      linea:'rgba(16,24,32,.10)', linea2:'rgba(16,24,32,.18)',
      texto:'#111820', texto2:'#39434e', apagado:'#68727e',
      sombra:'0 12px 30px rgba(16,24,32,.10)',
      ok:'#1a8f4c', atencion:'#a5730a', mal:'#c0353a', dato:'#2f6fb0',
      velo:'rgba(244,246,248,.62)', velo2:'rgba(244,246,248,.18)', velo3:'rgba(244,246,248,.94)',
      vidrio:'rgba(255,255,255,.82)', vidrioLinea:'rgba(16,24,32,.14)',
      sombraTexto:'0 1px 8px rgba(255,255,255,.75)'
    }
  };

  /* Qué nombre le puso cada pantalla a cada rol. La misma idea escrita de
     cinco maneras, que es lo que hay. */
  const NOMBRES = {
    fondo:   ['--bg', '--bg2', '--plane', '--b'],
    panel:   ['--panel', '--surface-1', '--p', '--card'],
    panel2:  ['--panel-2', '--surface-2', '--p2', '--card2'],
    panel3:  ['--surface-3', '--p3', '--raise'],
    linea:   ['--line', '--hairline', '--l', '--rule'],
    linea2:  ['--hairline-2', '--l2', '--rule2'],
    texto:   ['--ink', '--t'],
    texto2:  ['--ink-2', '--ink2'],
    apagado: ['--muted', '--ink-muted', '--m'],
    marca:   ['--orange', '--brand', '--o', '--acc', '--kpi-accent'],
    marcaSuave: ['--orange-soft', '--brand-soft', '--os', '--acc-soft'],
    marcaLinea: ['--acc-line'],
    marcaFuerte:['--brand-deep', '--acc-hi'],
    sombra:  ['--shadow'],
    ok:      ['--ok', '--green', '--st-good'],
    atencion:['--warn', '--w', '--st-warning'],
    mal:     ['--bad', '--red', '--st-critical'],
    dato:    ['--cyan', '--series-1'],
    velo:    ['--velo'], velo2: ['--velo-2'], velo3: ['--velo-3'],
    vidrio:  ['--vidrio'], vidrioLinea: ['--vidrio-linea'],
    sombraTexto: ['--sombra-texto']
  };

  /* Un color con transparencia, para los fondos suaves de la marca. */
  function conAlfa(hex, alfa){
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alfa})`;
  }

  function css(prefs){
    const claro = prefs.tema === 'claro' ||
      (prefs.tema === 'auto' && matchMedia('(prefers-color-scheme: light)').matches);
    const t = TEMAS[claro ? 'claro' : 'oscuro'];
    const marca = PALETAS[prefs.paleta] || PALETAS.diemar;

    const roles = Object.assign({}, t, {
      marca,
      marcaSuave: conAlfa(marca, claro ? 0.10 : 0.13),
      marcaLinea: conAlfa(marca, claro ? 0.28 : 0.32),
      marcaFuerte: marca
    });

    const lineas = [];
    for (const rol in NOMBRES)
      if (roles[rol] != null)
        for (const nombre of NOMBRES[rol]) lineas.push(`${nombre}:${roles[rol]};`);
    lineas.push(`color-scheme:${t.esquema};`);
    return `:root{${lineas.join('')}}`;
  }

  function aplicar(prefs){
    const claro = prefs.tema === 'claro' ||
      (prefs.tema === 'auto' && matchMedia('(prefers-color-scheme: light)').matches);
    let hoja = document.getElementById('tema-css');
    if (!hoja) {
      hoja = document.createElement('style');
      hoja.id = 'tema-css';
      /* Al final del head: tiene que ganarle a la hoja de la pantalla. */
      (document.head || document.documentElement).appendChild(hoja);
    }
    hoja.textContent = css(prefs);
    document.documentElement.dataset.tema = prefs.tema;
    document.documentElement.dataset.paleta = prefs.paleta;

    /* La portada. Es una variable de la hoja, así que no hay que pisar
       ningún selector: la pantalla la usa donde la use. */
    const propia = prefs.tiene_fondo && prefs.fondo_propio;
    document.documentElement.style.setProperty('--portada', propia
      ? `url('/api/fondo?v=${encodeURIComponent(prefs.fondo_version || '')}')`
      : '');
    if (!propia) document.documentElement.style.removeProperty('--portada');

    /* El logo. El de la aplicación es blanco y sobre fondo claro no se ve;
       el azul de las etiquetas sí. Es la misma marca en dos tintas. */
    for (const img of document.querySelectorAll('img[src^="/logo"]'))
      img.src = claro ? '/logo-cedula.png' : '/logo.png';
  }

  /* Lo último que se vio, para que la pantalla no arranque de un color y
     cambie al otro medio segundo después. Se guarda en el navegador y se
     refresca con lo que diga el servidor, que es el que manda. */
  const GUARDADO = 'taller.tema';
  let prefs = { tema:'oscuro', paleta:'diemar', tiene_fondo:false, fondo_propio:true };
  try {
    const antes = JSON.parse(localStorage.getItem(GUARDADO) || 'null');
    if (antes) prefs = Object.assign(prefs, antes);
  } catch (e) { /* sin memoria del navegador, se arranca con lo de siempre */ }
  aplicar(prefs);

  window.Tema = {
    actual: () => prefs,
    poner(nuevas){
      prefs = Object.assign({}, prefs, nuevas);
      aplicar(prefs);
      try { localStorage.setItem(GUARDADO, JSON.stringify(prefs)); } catch (e) {}
      return prefs;
    },
    /* Guardar en el servidor: es lo que hace que se vea igual en la
       computadora del taller y en el celular. */
    async guardar(nuevas){
      const p = window.Tema.poner(nuevas);
      const r = await fetch('/api/preferencias', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ tema:p.tema, paleta:p.paleta,
                               fondo_propio:p.fondo_propio })
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error ||
                                 'No se pudo guardar.');
      return window.Tema.poner(await r.json());
    }
  };

  /* Y lo que diga el servidor, apenas conteste. */
  fetch('/api/preferencias').then(r => r.ok ? r.json() : null).then(d => {
    if (d) window.Tema.poner(d);
  }).catch(() => {});

  /* Con el tema del sistema, seguirlo si el usuario lo cambia. */
  matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
    if (prefs.tema === 'auto') aplicar(prefs);
  });
})();
