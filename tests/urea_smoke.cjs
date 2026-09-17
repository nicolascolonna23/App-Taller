// La solapa de urea contra /api/urea simulada.
// Verifica lo que la pantalla promete: que el saldo se lea desde lejos,
// que el que no gestiona pueda despachar pero no cargar el tacho ni
// medirlo, que un despacho sin unidad exija motivo, y que la medición
// mande los litros medidos y no una corrección del saldo.
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
const dir = path.resolve(__dirname, '..');

const tanque = {
  tanque_id: 1, nombre: 'Tacho Catamarca', sucursal_codigo: 'CAT', activo: true,
  capacidad_litros: 1000, minimo_litros: 200, saldo: 140, porcentaje: 14,
  ultima_entrada: '2026-09-01', ultima_salida: '2026-09-16',
  ultima_medicion: '2026-09-10', consumo_diario: 16, dias_restantes: 9,
  estado: 'aviso',
};

const datos = (gestiona) => ({
  instalado: true,
  tanques: [tanque],
  movimientos: [
    {id: 3, tanque_id: 1, tanque: 'Tacho Catamarca', tipo: 'salida', fecha: '2026-09-16',
     litros: 40, delta: -40, unidad_id: 1, patente: 'AD247MQ', interno: '2', km: 124000,
     proveedor: null, remito: null, importe: null, motivo: null, medido_litros: null,
     usuario: 'Ramón', nota: null},
    {id: 2, tanque_id: 1, tanque: 'Tacho Catamarca', tipo: 'ajuste', fecha: '2026-09-10',
     litros: -12, delta: -12, unidad_id: null, patente: null, interno: null, km: null,
     proveedor: null, remito: null, importe: null, motivo: 'Merma del mes',
     medido_litros: 540, usuario: 'Nicolás', nota: null},
    {id: 1, tanque_id: 1, tanque: 'Tacho Catamarca', tipo: 'entrada', fecha: '2026-09-01',
     litros: 600, delta: 600, unidad_id: null, patente: null, interno: null, km: null,
     proveedor: 'Petrobras', remito: 'A-991', importe: 540000, motivo: null,
     medido_litros: null, usuario: 'Nicolás', nota: null},
  ],
  por_unidad: [
    {mes: '2026-09-01', unidad_id: 1, patente: 'AD247MQ', interno: '2', marca: 'SCANIA',
     modelo: 'R400', sucursal: 'CAT', chofer: 'Ramón', despachos: 3, litros_urea: 120,
     litros_gasoil: 3000, km: 9000, porcentaje_gasoil: 4, litros_100km: 1.33},
    {mes: '2026-09-01', unidad_id: 2, patente: 'AA823XJ', interno: '300', marca: 'IVECO',
     modelo: 'BS-170', sucursal: 'COR', chofer: 'Ana', despachos: 2, litros_urea: 90,
     litros_gasoil: 900, km: 2600, porcentaje_gasoil: 10, litros_100km: 3.46},
  ],
  banda_gasoil: [3, 6],
  unidades: [{id: 1, patente: 'AD247MQ', interno: '2', marca: 'SCANIA', modelo: 'R400',
              sucursal: 'CAT', chofer: 'Ramón', km_actual: 124500}],
  puede_gestionar: gestiona,
});

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_PATH ? {executablePath: process.env.BROWSER_PATH} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errores = [], pedidos = [];
    let gestiona = true;
    page.on('pageerror', e => errores.push(e.message));
    await page.route('**/*', route => {
      const req = route.request(), url = new URL(req.url());
      if (url.pathname === '/api/urea') {
        if (req.method() === 'GET') return route.fulfill({json: datos(gestiona)});
        const cuerpo = req.postDataJSON();
        pedidos.push(cuerpo);
        return route.fulfill({json: {ok: true, saldo: 100,
                                     aviso: 'Quedan 100 litros. Hay que pedir urea.'}});
      }
      if (url.pathname === '/api/yo')
        return route.fulfill({json: {nombre: 'Nicolás', rol: 'admin'}});
      if (url.pathname === '/api/combustible')
        return route.fulfill({json: {tickets: [], resumen: [], cruce: [], lotes: []}});
      if (url.pathname === '/logo.png')
        return route.fulfill({body: fs.readFileSync(path.join(dir, 'logo_diemar4.png')),
                              contentType: 'image/png'});
      if (url.pathname === '/combustible')
        return route.fulfill({body: fs.readFileSync(path.join(dir, 'combustible.html'), 'utf8'),
                              contentType: 'text/html'});
      return route.fulfill({status: 404, body: ''});
    });

    await page.goto('http://taller.test/combustible#urea');
    await page.locator('#u-tacho .litros').waitFor();

    // El saldo, de lejos: litros, porcentaje y para cuántos días alcanza.
    const tacho = await page.locator('#u-tacho').innerText();
    for (const x of ['140', '14% de 1.000 litros', '9 días', 'HAY QUE PEDIR'])
      assert(tacho.includes(x), `falta "${x}" en la tarjeta del tacho: ${tacho}`);
    assert.equal(await page.locator('.nivel.aviso').count(), 1,
                 'el nivel no está marcado como aviso');
    // La solapa de urea no importa archivos: la urea se carga a mano.
    assert.equal(await page.evaluate(() => getComputedStyle(
      document.querySelector('#imports')).display), 'none');

    // Los movimientos, con el signo puesto por el tipo.
    const filas = await page.locator('#u-movimientos tr').allInnerTexts();
    assert.equal(filas.length, 3);
    assert(filas[0].includes('-40'), 'el despacho no resta: ' + filas[0]);
    assert(filas[2].includes('+600'), 'la carga no suma: ' + filas[2]);
    assert(filas[1].includes('medido: 540'), 'la medición no muestra lo medido');

    // Despachar: sin unidad hay que decir el motivo.
    await page.click('#u-despachar');
    await page.fill('#u-form-salida input[name="litros"]', '40');
    await page.selectOption('#u-s-unidad', '1');
    assert.equal(await page.inputValue('#u-form-salida input[name="km"]'), '124500',
                 'no completó el km del maestro');
    await page.click('#u-form-salida button[type="submit"]');
    await page.waitForFunction(() => !document.querySelector('#u-aviso').hidden);
    const despacho = pedidos.find(p => p.op === 'despachar');
    assert.equal(despacho.litros, '40');
    assert.equal(despacho.unidad_id, '1');
    assert((await page.locator('#u-aviso').innerText()).includes('pedir urea'));

    // Medir: se manda lo medido, no una corrección del saldo.
    await page.click('#u-medir');
    await page.fill('#u-form-medicion input[name="medido_litros"]', '95');
    await page.fill('#u-form-medicion input[name="motivo"]', 'Merma');
    await page.click('#u-form-medicion button[type="submit"]');
    await page.waitForTimeout(200);
    const medicion = pedidos.find(p => p.op === 'medir');
    assert.equal(medicion.medido_litros, '95');
    assert.equal(medicion.motivo, 'Merma');

    // La urea por unidad: fuera de la banda 3–6% se marca.
    const fuera = await page.locator('#u-unidades .fuera').allInnerTexts();
    assert.deepEqual(fuera, ['10%'], 'no marcó la unidad fuera de banda: ' + fuera);

    // El que no gestiona despacha, pero no compra ni mide.
    gestiona = false;
    await page.reload();
    await page.locator('#u-tacho .litros').waitFor();
    assert(await page.locator('#u-despachar').isVisible(), 'no puede despachar');
    assert(!await page.locator('#u-cargar').isVisible(), 'puede cargar el tacho sin gestionar');
    assert(!await page.locator('#u-medir').isVisible(), 'puede medir sin gestionar');
    assert.equal(await page.locator('[data-borrar-urea]').count(), 0,
                 'puede borrar movimientos sin gestionar');

    await page.setViewportSize({width: 390, height: 844});
    assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
           'la solapa de urea desborda a lo ancho en el celular');
    await page.screenshot({path: '/tmp/urea.png', fullPage: true});
    assert.deepEqual(errores, []);
    console.log('PASS: saldo y días del tacho, signo por tipo de movimiento, despacho con ' +
                'km del maestro, medición por litros medidos, banda de urea y celular.');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
