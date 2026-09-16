// La pantalla de vales contra /api/vales simulada.
// Verifica lo que el circuito promete: que la bandeja ponga la unidad
// parada arriba de todo, que la sucursal no elija el número ni el estado,
// que aprobar y rechazar sean un clic, y que el vale impreso salga con el
// número, la unidad y las dos firmas.
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
const dir = path.resolve(__dirname, '..');

const ahora = new Date();
const hace = min => new Date(ahora - min * 60000).toISOString();

const vale = (extra) => Object.assign({
  id: 'CAT-00001', sucursal_codigo: 'CAT', sucursal: 'Catamarca', numero: 1,
  unidad_id: 1, patente: 'AD247MQ', interno: '2', marca: 'SCANIA', modelo: 'R400',
  km: 123000, tipo: 'CORRECTIVO', origen: 'CHECKLIST', urgencia: 'PUEDE_ESPERAR',
  detalle: 'Pierde aire el sistema de frenos', taller_sugerido: 'Frenos del Valle',
  taller: null, monto_estimado: 80000, monto_autorizado: null, monto: 80000,
  estado: 'SOLICITADO', solicitante: 'Ramón', fecha_hecho: '2026-09-14',
  creado_en: hace(30), nota: null, factura_numero: null,
  regularizacion_ruta: false, vale_anterior: null, aprobado_por: null,
  orden_numero: null, demorado: false, chofer: 'Ana',
}, extra);

const datos = {
  vales: [
    vale({}),
    vale({id: 'COR-00047', sucursal_codigo: 'COR', sucursal: 'Córdoba', numero: 47,
          patente: 'AA823XJ', interno: '300', urgencia: 'UNIDAD_PARADA',
          detalle: 'Se cortó la correa en Recreo', origen: 'RUTA',
          creado_en: hace(10), demorado: true, monto_estimado: null, monto: null}),
    vale({id: 'CAT-00002', numero: 2, estado: 'CERRADO', tipo: 'PREVENTIVO',
          detalle: 'Service de 130.000', factura_numero: 'A-7',
          monto_autorizado: 400000, monto: 400000, aprobado_por: 'Nicolás'}),
  ],
  resumen: {SOLICITADO: 2, APROBADO: 0, EN_EJECUCION: 0, CERRADO: 1, RECHAZADO: 0,
            demorados: 1, parados: 1, sin_rendir: 1},
  sucursales: [{codigo: 'CAT', nombre: 'Catamarca', activa: true},
               {codigo: 'COR', nombre: 'Córdoba', activa: true}],
  unidades: [{id: 1, patente: 'AD247MQ', interno: '2', marca: 'SCANIA',
              modelo: 'R400', sucursal: 'CAT', chofer: 'Ana', km_actual: 123400}],
  lista_blanca: ['Lámparas, fusibles y plumillas', 'Inflado, parche o auxilio en ruta'],
  usuario: {nombre: 'Ramón', sucursal_codigo: 'CAT', puede_aprobar: true},
  exigir_vale: true,
};

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_PATH ? {executablePath: process.env.BROWSER_PATH} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errores = [], pedidos = [];
    page.on('pageerror', e => errores.push(e.message));
    await page.route('**/*', route => {
      const req = route.request(), url = new URL(req.url());
      if (url.pathname === '/api/vales') {
        if (req.method() === 'GET') return route.fulfill({json: datos});
        const cuerpo = req.postDataJSON();
        pedidos.push(cuerpo);
        if (cuerpo.op === 'ficha')
          return route.fulfill({json: {
            vale: datos.vales.find(v => v.id === cuerpo.id),
            eventos: [{estado: 'SOLICITADO', usuario: 'Ramón',
                       momento: hace(30), comentario: null}]}});
        if (cuerpo.op === 'crear')
          return route.fulfill({json: {ok: true, id: 'CAT-00003', numero: 3,
                                       sucursal_codigo: 'CAT'}});
        return route.fulfill({json: {ok: true, id: cuerpo.id, estado: 'APROBADO'}});
      }
      if (url.pathname === '/logo.png')
        return route.fulfill({body: fs.readFileSync(path.join(dir, 'logo_diemar4.png')),
                              contentType: 'image/png'});
      if (url.pathname === '/vales')
        return route.fulfill({body: fs.readFileSync(path.join(dir, 'vales.html'), 'utf8'),
                              contentType: 'text/html'});
      return route.fulfill({status: 404, body: ''});
    });

    await page.goto('http://taller.test/vales');
    await page.locator('#filas tr').first().waitFor();

    // La bandeja: solo lo que espera respuesta, y la unidad parada arriba.
    assert.equal(await page.locator('#filas tr').count(), 2);
    assert.match(await page.locator('#filas tr').first().textContent(), /COR-00047/);
    assert.match(await page.locator('#filas tr').first().textContent(), /Sin respuesta/);
    assert.equal(await page.locator('#n-parados').textContent(), '1');
    assert.equal(await page.locator('#n-rendir').textContent(), '1');

    // Mi sucursal y toda la red: la misma lista, otro recorte.
    await page.click('[data-vista="mia"]');
    assert.equal(await page.locator('#filas tr').count(), 2);
    await page.click('[data-vista="red"]');
    assert.equal(await page.locator('#filas tr').count(), 3);
    await page.fill('#buscar', 'correa');
    assert.equal(await page.locator('#filas tr').count(), 1);
    await page.fill('#buscar', '');

    // El formulario: la sucursal no elige número ni estado, y el que tiene
    // sucursal cargada no ve el desplegable.
    await page.click('#nuevo');
    assert(!await page.locator('#cajaSucursal').isVisible());
    assert.equal(await page.locator('#listaBlanca li').count(), 2);
    await page.selectOption('#vUnidad', '1');
    assert.equal(await page.inputValue('#vKm'), '123400');   // el km del maestro
    await page.fill('#vDetalle', 'Ruido en el tren delantero');
    await page.selectOption('#vUrgencia', 'OPERA_CON_RIESGO');
    await page.click('#guardarNuevo');
    await page.waitForFunction(() => document.querySelector('#modalVale').classList.contains('on'));
    const creado = pedidos.find(p => p.op === 'crear');
    assert.equal(creado.urgencia, 'OPERA_CON_RIESGO');
    assert.equal(creado.km, '123400');
    assert(!('id' in creado) && !('estado' in creado), 'la sucursal no manda número ni estado');

    // El vale abierto: aprobar y rechazar en un clic, y el papel que se firma.
    await page.click('[data-cerrar="modalVale"]');
    await page.click('[data-vale="CAT-00001"]');
    await page.locator('#cuerpoVale .ficha-cab').waitFor();
    assert.equal(await page.locator('[data-op="aprobar"]').count(), 1);
    assert.equal(await page.locator('[data-op="rechazar"]').count(), 1);
    page.once('dialog', d => d.accept('90000'));
    page.once('dialog', d => d.accept('Frenos del Valle'));
    await page.evaluate(() => {
      window.print = () => { window.imprimio = true; };
    });
    await page.click('#imprimirVale');
    const hoja = await page.locator('#hoja').innerHTML();
    for (const x of ['CAT-00001', 'AD 247 MQ', 'Solicitó', 'Autorizó', 'Pierde aire'])
      assert(hoja.includes(x), `falta "${x}" en el vale impreso`);

    // Un cerrado no ofrece botones de circuito: ya está.
    await page.click('[data-cerrar="modalVale"]');
    await page.click('[data-vale="CAT-00002"]');
    await page.locator('#cuerpoVale .ficha-cab').waitFor();
    assert.equal(await page.locator('[data-op]').count(), 0);
    await page.click('[data-cerrar="modalVale"]');

    // En el celular la pantalla no se va de ancho: el vale se carga desde
    // el teléfono, al lado de la unidad.
    await page.setViewportSize({width: 390, height: 844});
    assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
           'la pantalla de vales desborda a lo ancho en el celular');
    assert.deepEqual(errores, []);
    console.log('PASS: bandeja por urgencia, mi sucursal y la red, alta sin número ' +
                'ni estado, aprobar/rechazar en un clic, vale impreso y celular.');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
