// La tarjeta de costos del taller en la portada, contra /api/inicio simulada.
// Verifica lo que el panel promete: el gasto por patente, el peso por
// kilómetro separado en preventivo y correctivo, y que lo que no se puede
// calcular se muestre vacío en vez de inventado.
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
const dir = path.resolve(__dirname, '..');

const costos = {
  desde: '2025-10-01', hasta: '2026-09-14', meses: 12,
  gasto: {total: 3400000, correctivo: 2000000, preventivo: 1200000,
          sin_clasificar: 200000, ordenes: 27, unidades: 3},
  flota: {km: 400000, gasto_medido: 3200000, pesos_km: 8, pesos_km_correctivo: 5,
          pesos_km_preventivo: 3, unidades_con_km: 2, unidades_sin_km: 1},
  unidades: [
    {patente: 'AH522SI', interno: '17', marca: 'IVECO', ordenes: 12, total: 2400000,
     correctivo: 1600000, preventivo: 800000, sin_clasificar: 0, km: 300000,
     km_desde: '2025-10-02', km_hasta: '2026-09-13',
     pesos_km: 8, pesos_km_correctivo: 5.33, pesos_km_preventivo: 2.67, parcial: false},
    {patente: 'AG797NJ', interno: '102', marca: 'TOYOTA', ordenes: 9, total: 800000,
     correctivo: 400000, preventivo: 400000, sin_clasificar: 0, km: 100000,
     km_desde: '2026-01-05', km_hasta: '2026-09-13',
     pesos_km: 8, pesos_km_correctivo: 4, pesos_km_preventivo: 4, parcial: true},
    {patente: 'AC111ZZ', interno: 'S1', marca: '', ordenes: 6, total: 200000,
     correctivo: 0, preventivo: 0, sin_clasificar: 200000, km: null,
     km_desde: null, km_hasta: null,
     pesos_km: null, pesos_km_correctivo: null, pesos_km_preventivo: null, parcial: false},
  ],
  resto: {unidades: 0, total: 0},
  serie: [{mes: '2026-02-01', correctivo: 2000000, preventivo: 1200000,
           sin_clasificar: 200000, total: 3400000}],
};

const inicio = {
  unidades: 87, reponer: 3, ordenes_abiertas: 4,
  recorrido: {ayer: {km: 12345, unidades: 50, unidades_completas: 50,
                     desde: '2026-09-13', hasta: '2026-09-13', serie: []}},
  combustible: null, alertas: {total: 2, graves: 1},
  ordenes_costos: costos,
};

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_PATH ? {executablePath: process.env.BROWSER_PATH} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1200}});
    const errores = [];
    page.on('pageerror', e => errores.push(e.message));
    let datos = inicio;

    await page.route('**/*', route => {
      const url = new URL(route.request().url()), p = url.pathname;
      if (p === '/api/yo') return route.fulfill({json: {nombre: 'Prueba', rol: 'admin'}});
      if (p === '/api/inicio') return route.fulfill({json: datos});
      if (p === '/api/alertas') return route.fulfill({json: {instalado: true, resumen: {total: 0}, alertas: []}});
      if (p.startsWith('/api/')) return route.fulfill({status: 503, json: {error: 'sin datos'}});
      if (p === '/') return route.fulfill({body: fs.readFileSync(path.join(dir, 'inicio.html'), 'utf8'), contentType: 'text/html'});
      const archivo = path.join(dir, p.slice(1));
      if (archivo.startsWith(dir + path.sep) && fs.existsSync(archivo) && fs.statSync(archivo).isFile())
        return route.fulfill({body: fs.readFileSync(archivo),
          contentType: p.endsWith('.js') ? 'text/javascript' : p.endsWith('.css') ? 'text/css' : 'image/png'});
      return route.abort();
    });

    await page.goto('http://taller.test/');
    await page.locator('#cost-table table').waitFor();

    // Los tres números de arriba, tal como los pidió el taller.
    assert.equal(await page.textContent('#cost-corr'), '$ 5,00');
    assert.equal(await page.textContent('#cost-prev'), '$ 3,00');
    assert.match(await page.textContent('#cost-total'), /3\.400\.000/);
    assert.match(await page.textContent('#cost-total-sub'), /27 órdenes/);

    // El ranking por patente, con la patente legible y su gasto.
    const filas = page.locator('#cost-table tbody tr');
    assert.equal(await filas.count(), 3);
    assert.match(await filas.first().textContent(), /AH 522 SI/);
    assert.match(await filas.first().textContent(), /2\.400\.000/);
    assert.match(await filas.first().textContent(), /300\.000 km/);

    // La unidad sin lecturas muestra el gasto y deja el peso por km vacío:
    // un cero ahí sería decir que mantenerla no cuesta nada por kilómetro.
    const sinKm = filas.nth(2);
    assert.match(await sinKm.textContent(), /AC 111 ZZ/);
    assert.equal((await sinKm.locator('td.num').nth(1).textContent()).trim(), '—');
    assert.match(await page.textContent('#cost-note'), /1 sin lecturas/);
    assert.match(await page.textContent('#cost-note'), /sin clasificar/);

    // La barra reparte el gasto entre las tres clases.
    assert.equal(await page.locator('#cost-split .cost-bar > span').count(), 3);

    await page.screenshot({path: '/tmp/inicio-costos.png', fullPage: true});

    // Sin órdenes cargadas la tarjeta lo dice, no se queda cargando.
    datos = {...inicio, ordenes_costos: null};
    await page.reload();
    await page.locator('#cost-table .dashboard-empty').waitFor();
    assert.equal(await page.textContent('#cost-corr'), '—');

    // En el celular no puede desbordar a lo ancho.
    await page.setViewportSize({width: 390, height: 844});
    datos = inicio;
    await page.reload();
    await page.locator('#cost-table table').waitFor();
    assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
           'la portada desborda a lo ancho en el celular');

    assert.deepEqual(errores, []);
    console.log('PASS: costos del taller — $/km preventivo y correctivo, ranking por patente, sin lecturas, vacío y celular.');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
