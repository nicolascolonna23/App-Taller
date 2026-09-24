// La pantalla de Flota: el chasis al lado de la patente, las dos salidas y
// la baja. Las direcciones de /api las contesta este mismo archivo, así que
// esto NO prueba el ruteo del servidor: de eso se ocupa tests/test_rutas.py,
// que existe porque el Excel se rompió justamente ahí y acá no se vio.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
const RAIZ = path.join(__dirname, '..');

const unidades = [
  { id:1, patente:'AH522SI', chasis:'93ZS62RUZS8607035', interno:'17', marca:'IVECO',
    modelo:'S-WAY 480', chofer:'CABRERA', semi:'AC538KW', sucursal:'LAD',
    uso:'LARGA DISTANCIA', tipo:'vehiculo', activa:true },
  { id:2, patente:'KOF186', chasis:'8AJFR22P5M1234567', interno:'80', marca:'TOYOTA',
    modelo:'HIACE', chofer:'PEREZ', semi:'', sucursal:'CAT',
    uso:'DISTRIBUCION LOCAL', tipo:'vehiculo', activa:true },
  { id:3, patente:'AE988UW', chasis:'93ZS62RUZS8600001', interno:'9', marca:'IVECO',
    modelo:'STRALIS', chofer:'', semi:'', sucursal:'LAD',
    uso:'LARGA DISTANCIA', tipo:'vehiculo', activa:false },
];

(async () => {
  const browser = await chromium.launch({ headless:true,
    ...(process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : {}) });
  try {
    const page = await browser.newPage({ viewport:{ width:1440, height:1000 } });
    const errores = [], enganches = []; page.on('pageerror', e => errores.push(e.message));
    let pedidoExcel = null; const bajas = [], lotes = [];

    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      const p = url.pathname;
      if (p === '/api/yo') return route.fulfill({ json:{ nombre:'Prueba', rol:'admin' } });
      if (p === '/api/unidades/exportar') {
        pedidoExcel = url.searchParams.get('ids');
        return route.fulfill({ status:200, contentType:'application/octet-stream', body:'xlsx' });
      }
      if (p === '/api/unidades' && route.request().method() === 'POST') {
        const cuerpo = route.request().postDataJSON();
        // El mismo cambio sobre varias: residencia y marca de semi.
        if (cuerpo.op === 'lote') {
          lotes.push(cuerpo);
          for (const id of cuerpo.ids) {
            const u = unidades.find(x => x.id === id);
            if (!u) continue;
            if (cuerpo.sucursal) u.sucursal = cuerpo.sucursal.toUpperCase();
            if (cuerpo.es_semi) u.uso = 'SEMIRREMOLQUE';
          }
          return route.fulfill({ json:{ cambiadas:cuerpo.ids.length, patentes:[] } });
        }
        bajas.push(cuerpo);
        const u = unidades.find(x => x.id === cuerpo.id);
        if (u) u.activa = !!cuerpo.activa;
        return route.fulfill({ json:{ activa:!!cuerpo.activa, unidad:u,
          aviso: cuerpo.activa ? 'Vuelve a la operación.'
               : 'Queda de baja. Ojo: tenía 2 cubiertas montadas.' } });
      }
      if (p === '/api/unidades') return route.fulfill({ json:{
        unidades, sucursales:['LAD','CAT'], usos:['LARGA DISTANCIA','DISTRIBUCION LOCAL'],
        configuraciones:[], revisar:[], armados:[], planes_mantenimiento:[] } });
      // La ficha de una unidad: lo que sabe el resto del sistema.
      const ficha = p.match(/^\/api\/unidades\/(\d+)$/);
      if (ficha) {
        const u = unidades.find(x => String(x.id) === ficha[1]);
        return route.fulfill({ json:{ unidad:u, modelo_3d:null, modelo_3d_falta:null,
          odometro:null, lecturas:[], cubiertas:[], vencimientos:[],
          // Lo que pasó por el taller, como lo arma el módulo de órdenes.
          ordenes:{ patente:u.patente, total:340000,
            ordenes:[
              { numero:91, fecha:'2026-09-14', estado:'abierta', tipo:'interna',
                mantenimiento:'correctivo', taller:null, total:90000,
                solicitado:'Pierde aire el sistema de frenos', diagnostico:null,
                factura:null },
              { numero:82, fecha:'2026-08-02', estado:'cerrada', tipo:'externa',
                mantenimiento:'preventivo', taller:'Iveco Catamarca', total:250000,
                solicitado:'Service de 130.000', diagnostico:null, factura:'A-7' },
              { numero:70, fecha:'2026-05-11', estado:'anulada', tipo:'interna',
                mantenimiento:'correctivo', taller:null, total:12000,
                solicitado:'Cargada por error', diagnostico:null, factura:null },
            ],
            trabajos:[{ numero:82, fecha:'2026-08-02', estado:'cerrada',
                        detalle:'Cambio de aceite y filtros' }],
            repuestos:[{ numero:82, fecha:'2026-08-02', codigo:'F-101',
                         descripcion:'Filtro de aceite', cantidad:2 }] },
          services:[], posiciones:[] } });
      }
      // El submódulo tractor–semi: el semi no reporta, sus km son los
      // del tractor que lo llevó.
      if (p === '/api/enganches') {
        if (route.request().method() === 'POST') {
          enganches.push(route.request().postDataJSON());
          return route.fulfill({ json:{ ok:true } });
        }
        return route.fulfill({ json:{
          semis:[{ semi_id:9, patente:'AE456MJ', interno:'S1', marca:'RANDON', modelo:'SR',
                   sucursal:'CAT', km_actual:1600, activa:true, enganche_id:3, tractor_id:1,
                   desde:'2026-09-14', tractor:'AH522SI', tractor_interno:'17',
                   km_enganchado:1600, ultimo_dia:'2026-09-17', enganches:2 },
                 { semi_id:10, patente:'AE456MK', interno:'S2', marca:'RANDON', modelo:'SR',
                   sucursal:'CAT', km_actual:null, activa:true, enganche_id:null,
                   tractor_id:null, desde:null, tractor:null, tractor_interno:null,
                   km_enganchado:0, ultimo_dia:null, enganches:0 }],
          tractores:[{ id:1, patente:'AH522SI', interno:'17', sucursal:'CAT', km_actual:412300,
                       semi_id:9, semi:'AE456MJ' }],
          candidatos:[{ id:9, patente:'AE456MJ', interno:'S1', es_semi:true },
                      { id:10, patente:'AE456MK', interno:'S2', es_semi:true }],
          puede_gestionar:true } });
      }
      if (p.startsWith('/api/')) return route.fulfill({ json:{} });
      const archivo = { '/unidades':'unidades.html', '/sistema.css':'sistema.css',
                        '/tema.js':'tema.js', '/camion3d.js':'camion3d.js' }[p];
      if (archivo) return route.fulfill({ body: fs.readFileSync(path.join(RAIZ, archivo),'utf8'),
        contentType: archivo.endsWith('.css') ? 'text/css'
                   : archivo.endsWith('.js') ? 'text/javascript' : 'text/html' });
      return route.fulfill({ status:404, body:'' });
    });

    await page.goto('http://taller.test/unidades');
    await page.locator('#cuerpo tr').first().waitFor();

    // ---- el chasis al lado de la patente ------------------------------
    // Las columnas de datos: la primera es la del casillero para tildar.
    const cab = await page.locator('#cabecera th[data-k]').allInnerTexts();
    assert.equal(cab[0].trim().toUpperCase().replace(/\s*[▲▼]$/,''), 'PATENTE', 'la 1ª no es Patente: ' + cab[0]);
    assert.equal(cab[1].trim().toUpperCase().replace(/\s*[▲▼]$/,''), 'CHASIS', 'la 2ª no es Chasis: ' + cab[1]);
    assert.equal(cab.filter(t => /CHASIS/i.test(t)).length, 1, 'el chasis quedó dos veces');
    const fila1 = await page.locator('#cuerpo tr').first().locator('td:not(.tilde-col)').allInnerTexts();
    assert(/^\d|^[0-9A-Z]{10,}/.test(fila1[1].trim()), 'la 2ª celda no es el chasis: ' + fila1[1]);

    // ---- Excel: manda lo que se ve ------------------------------------
    await page.click('#exp-excel');
    await page.waitForFunction(() => true);
    await page.waitForTimeout(300);
    assert.equal(pedidoExcel, '1,2', 'el Excel no pidió las unidades visibles: ' + pedidoExcel);

    // con un filtro puesto, exporta solo eso
    pedidoExcel = null;
    await page.selectOption('#f-sucursal', 'CAT');
    await page.click('#exp-excel');
    await page.waitForTimeout(300);
    assert.equal(pedidoExcel, '2', 'el filtro no llegó al Excel: ' + pedidoExcel);

    // las bajas entran cuando se piden
    pedidoExcel = null;
    await page.selectOption('#f-sucursal', '');
    await page.selectOption('#f-estado', 'todas');
    await page.click('#exp-excel');
    await page.waitForTimeout(300);
    assert.equal(pedidoExcel, '3,1,2', 'no entró la unidad de baja, o cambió el orden de pantalla: ' + pedidoExcel);

    // ---- PDF: abre la ventana de impresión con la tabla ---------------
    await page.addInitScript(() => { window.print = () => { window.__imprimio = true; }; });
    const [vent] = await Promise.all([ page.context().waitForEvent('page'), page.click('#exp-pdf') ]);
    await vent.waitForLoadState('domcontentloaded');
    const filas = await vent.locator('tbody tr').count();
    assert.equal(filas, 3, 'el PDF no trajo las 3 unidades: ' + filas);
    const enc = await vent.locator('thead th').allInnerTexts();
    assert.equal(enc[1].toUpperCase(), 'CHASIS', 'el PDF no tiene el chasis segundo');
    assert.equal(await vent.locator('tr.baja').count(), 1, 'el PDF no marca la unidad de baja');
    const sub = await vent.locator('.sub').innerText();
    assert(sub.includes('3 unidades'), 'el PDF no dice cuántas: ' + sub);
    assert(await vent.locator('.nota').count() === 1, 'el PDF no aclara qué significa el tachado');
    await vent.screenshot({ path:'/tmp/flota-pdf.png', fullPage:true });
    await vent.close();

    // ---- el historial de taller de la unidad --------------------------
    // Abrir un camión y no ver qué se le hizo obligaba a ir a otra
    // pantalla. Acá tiene que estar: abiertas, cerradas y lo que costó.
    await page.click('#cuerpo tr:has-text("AH 522 SI")');
    await page.locator('#c-estado').waitFor({ state:'visible' });
    const taller = page.locator('.bloque', { hasText:'Órdenes de trabajo' });
    await taller.waitFor();
    const texto = await taller.innerText();
    for (const x of ['1', 'abiertas', 'cerradas', 'Nº 91', 'Nº 82',
                     'Pierde aire', 'Cambio de aceite y filtros',
                     'Filtro de aceite', 'Iveco Catamarca', 'Factura A-7'])
      assert(texto.includes(x), `falta "${x}" en el historial de taller: ${texto}`);
    // La anulada se lista, pero su monto no suma: el trabajo no existió.
    assert(texto.includes('Nº 70') && texto.includes('anulada'),
           'la orden anulada no aparece');
    assert(texto.includes('340.000'), 'el gastado no es el de las no anuladas: ' + texto);
    assert(!texto.includes('$ 12.000'), 'la anulada está mostrando monto');
    await page.click('#cerrar');

    // ---- el mismo cambio sobre varias unidades -------------------------
    // El maestro entra sin residencia y sin decir cuál es semi: de a una
    // son cuarenta fichas, así que se tildan y se cambian juntas.
    {
      await page.locator('#tilde-todas').waitFor();
      assert(await page.locator('#lote').isHidden(), 'la barra del lote se ve sin nada tildado');
      await page.click('#tilde-todas');
      await page.locator('#lote').waitFor();
      const cuantas = await page.locator('#cuerpo tr').count();
      assert((await page.locator('#lote-cuantas').innerText()).startsWith(String(cuantas)),
             'no dice cuántas quedaron tildadas');
      // La que no va se destilda: es el caso real, todas menos una.
      await page.click('#cuerpo tr:has-text("AH 522 SI") [data-tilde]');
      assert((await page.locator('#lote-cuantas').innerText()).startsWith(String(cuantas - 1)));
      // Tildar no abre la ficha: el clic en el casillero es otra cosa.
      assert(await page.locator('#fondo').isHidden(), 'tildar abrió la ficha');
      // Sin decir qué cambiar, no se manda nada.
      await page.click('#lote-aplicar');
      assert.equal(lotes.length, 0, 'mandó un lote sin decir qué cambiar');
      assert(!await page.locator('#error').isHidden(), 'no avisa que falta elegir qué cambiar');
      await page.fill('#l-sucursal', 'lad');
      await page.selectOption('#l-semi', '1');
      await page.click('#lote-aplicar');
      await page.waitForFunction(() => document.querySelector('#lote').hidden);
      assert.equal(lotes.length, 1);
      assert.equal(lotes[0].sucursal, 'lad');
      assert.equal(lotes[0].es_semi, true);
      assert(!lotes[0].ids.includes(1), 'mandó la que se había destildado');
      assert((await page.locator('#cuerpo').innerText()).includes('SEMIRREMOLQUE'),
             'la tabla no muestra el cambio');
    }

    // ---- asociación de equipos ----------------------------------------
    assert.equal((await page.locator('[data-vista="semis"]').innerText()).trim(),
                 'Asociación de equipos');
    await page.click('[data-vista="semis"]');
    await page.locator('#cuerpo-semis tr').first().waitFor();
    // El listado se explica solo: qué es cada fila y qué dice cada columna.
    const ayuda = await page.locator('#semis-ayuda').evaluate(e => e.textContent);
    for (const x of ['Tractor de hoy', 'Suelto', 'Km enganchado', 'Km del semi'])
      assert(ayuda.includes(x), `la ayuda del listado no explica "${x}": ${ayuda}`);
    assert((await page.locator('#v-semis > .sub').first().innerText()).includes('no tiene satelital'),
           'no dice de dónde salen los kilómetros de un equipo');
    assert((await page.locator('#semis-sub').innerText()).includes('1 enganchado hoy'),
           'el resumen no dice cuántos están enganchados');
    const semis = await page.locator('#cuerpo-semis').innerText();
    for (const x of ['AE 456 MJ', 'AH 522 SI', '1.600', 'suelto'])
      assert(semis.includes(x), `falta "${x}" en la asociación de equipos: ${semis}`);
    // El que está suelto no ofrece desenganchar: no hay nada que soltar.
    assert.equal(await page.locator('[data-desenganchar]').count(), 1);
    await page.click('#enganchar');
    await page.selectOption('#e-tractor', '1');
    await page.selectOption('#e-semi', '10');
    await page.click('#form-enganche button[type="submit"]');
    await page.waitForTimeout(250);
    const enganche = enganches.find(e => e.op === 'enganchar');
    assert.equal(enganche.tractor_id, '1');
    assert.equal(enganche.semi_id, '10');
    await page.click('[data-vista="unidades"]');

    // ---- dar de baja y reactivar --------------------------------------
    page.on('dialog', d => d.accept());
    await page.selectOption('#f-estado', 'activas');
    await page.click('#cuerpo tr:has-text("AH 522 SI")');
    await page.locator('#baja').waitFor({ state:'visible' });
    assert.equal((await page.locator('#baja').innerText()).trim(), 'Dar de baja');
    await page.click('#baja');
    await page.waitForFunction(() => !document.querySelector('#ficha-aviso').hidden);
    assert.deepEqual(bajas.at(-1), { op:'baja', id:1, activa:false });
    assert((await page.locator('#ficha-aviso').innerText()).includes('cubiertas montadas'),
           'la baja no avisa qué quedó colgando');
    assert.equal((await page.locator('#baja').innerText()).trim(), 'Reactivar',
                 'el botón no cambió a Reactivar');

    await page.click('#baja');
    await page.waitForFunction(() => document.querySelector('#baja').textContent.trim() === 'Dar de baja');
    assert.deepEqual(bajas.at(-1), { op:'baja', id:1, activa:true });

    await page.click('#cerrar');
    await page.screenshot({ path:'/tmp/flota-listado.png', fullPage:true });
    assert.deepEqual(errores, [], 'errores de JS: ' + errores.join(' | '));
    console.log('PASS: chasis 2ª columna; cambio en lote de residencia y semi; asociación de equipos explicada; Excel y PDF exportan lo filtrado; la ficha muestra el historial de taller con montos; el semi toma los km del tractor; baja y reactivación avisan qué queda colgando.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
