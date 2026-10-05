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
   ===================================================================== */
(function () {
  'use strict';

  /* El color de cada paleta. Lo demás sale de él. La primera es la de
     Titán Flota; conserva el id «diemar» porque es el que está guardado en
     las preferencias de cada usuario. */
  const PALETAS = {
    diemar:'#2563eb', naranja:'#f4791f', azul:'#3d8bfd', verde:'#22a06b',
    violeta:'#8b7bf7', rojo:'#e5484d', grafito:'#8a94a0'
  };

  /* Los dos temas, en roles. El claro no es el oscuro dado vuelta: el
     papel tiene que ser papel y la tinta, tinta. */
  const TEMAS = {
    /* Azul noche: el mismo fondo de la barra de navegación, con paneles un
       punto más claros. Sin negros puros ni brillos. */
    oscuro: {
      esquema:'dark',
      fondo:'#0c1726', panel:'#14243a', panel2:'#1b2e48', panel3:'#243a57',
      linea:'rgba(255,255,255,.09)', linea2:'rgba(255,255,255,.17)',
      texto:'#f4f6f8', texto2:'#d5dde8', apagado:'#9eaec2',
      sombra:'0 8px 24px rgba(0,0,0,.28)',
      ok:'#3ccf85', atencion:'#f4b740', mal:'#f2777a', dato:'#86b4ff',
      velo:'rgba(12,23,38,.55)', velo2:'rgba(12,23,38,.14)', velo3:'rgba(12,23,38,.90)',
      vidrio:'rgba(20,36,58,.86)', vidrioLinea:'rgba(255,255,255,.14)',
      sombraTexto:'0 2px 12px rgba(0,0,0,.6)',
      nav:'#0f1d30', navTexto:'#ffffff', navApagado:'rgba(255,255,255,.72)',
      navLinea:'rgba(255,255,255,.10)', navHover:'rgba(255,255,255,.08)'
    },
    /* La identidad de Titán Flota: fondo gris muy claro, superficies
       blancas, texto azul noche y el azul brillante para lo que se toca. */
    claro: {
      esquema:'light',
      fondo:'#f4f6f8', panel:'#ffffff', panel2:'#f0f3f7', panel3:'#e4e9f0',
      linea:'#e1e6ed', linea2:'#c9d2de',
      texto:'#14243a', texto2:'#34465f', apagado:'#5a6b80',
      sombra:'0 1px 2px rgba(20,36,58,.06), 0 6px 16px rgba(20,36,58,.06)',
      ok:'#15803d', atencion:'#a15c07', mal:'#b91c1c', dato:'#1d4ed8',
      velo:'rgba(244,246,248,.60)', velo2:'rgba(244,246,248,.16)', velo3:'rgba(244,246,248,.94)',
      vidrio:'rgba(255,255,255,.92)', vidrioLinea:'rgba(20,36,58,.12)',
      sombraTexto:'none',
      nav:'#14243a', navTexto:'#ffffff', navApagado:'rgba(255,255,255,.74)',
      navLinea:'rgba(255,255,255,.12)', navHover:'rgba(255,255,255,.08)'
    }
  };

  /* Qué nombre le puso cada pantalla a cada rol. La misma idea escrita de
     cinco maneras, que es lo que hay. */
  const NOMBRES = {
    fondo:   ['--bg', '--bg2', '--plane', '--b'],
    panel:   ['--panel', '--surface-1', '--p', '--card'],
    panel2:  ['--panel-2', '--surface-2', '--p2', '--card2'],
    panel3:  ['--panel-3', '--surface-3', '--p3', '--raise'],
    linea:   ['--line', '--hairline', '--l', '--rule'],
    linea2:  ['--line-2', '--hairline-2', '--l2', '--rule2'],
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
    sombraTexto: ['--sombra-texto'],
    /* La barra de navegación de Titán Flota: azul noche en los dos temas. */
    nav: ['--tf-nav'], navTexto: ['--tf-nav-ink'], navApagado: ['--tf-nav-muted'],
    navLinea: ['--tf-nav-line'], navHover: ['--tf-nav-hover']
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
      marcaSuave: conAlfa(marca, claro ? 0.09 : 0.16),
      marcaLinea: conAlfa(marca, claro ? 0.28 : 0.40),
      marcaFuerte: marca
    });

    const lineas = [];
    for (const rol in NOMBRES)
      if (roles[rol] != null)
        for (const nombre of NOMBRES[rol]) lineas.push(`${nombre}:${roles[rol]}!important;`);
    const canales = marca.slice(1).match(/../g).map(c => parseInt(c,16)/255).map(c => c <= .04045 ? c/12.92 : ((c+.055)/1.055)**2.4);
    const luminancia = canales[0]*.2126 + canales[1]*.7152 + canales[2]*.0722;
    lineas.push(`--marca-ink:${luminancia > .179 ? '#101419' : '#ffffff'};`);
    lineas.push(`color-scheme:${t.esquema}!important;`);
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
    document.documentElement.dataset.modo = claro ? 'claro' : 'oscuro';
    document.documentElement.dataset.paleta = prefs.paleta;


  }

  /* Lo último que se vio, para que la pantalla no arranque de un color y
     cambie al otro medio segundo después. Se guarda en el navegador y se
     refresca con lo que diga el servidor, que es el que manda. */
  const GUARDADO = 'taller.tema';
  let prefs = { tema:'claro', paleta:'diemar', diseno:2 };
  try {
    const antes = JSON.parse(localStorage.getItem(GUARDADO) || 'null');
    /* Lo guardado antes del rediseño de Titán Flota arrancaba en oscuro
       por defecto: se ignora el tema y se estrena el claro. */
    if (antes) prefs = Object.assign(prefs, antes,
      (antes.diseno || 0) < 2 ? { tema:'claro', diseno:2 } : {});
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
        body: JSON.stringify({ tema:p.tema, paleta:p.paleta })
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
