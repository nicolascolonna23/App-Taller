// La solapa de fluidos contra /api/fluidos simulada.
// Verifica lo que la pantalla promete: que el envase se vea lleno o vacío
// según lo que queda —y que los que están sin abrir se cuenten al lado—,
// que el que no gestiona pueda despachar pero no comprar ni medir, que un
// despacho sin unidad exija motivo, y que la medición mande lo medido y no
// una corrección del saldo.
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
const dir = path.resolve(__dirname, '..');

const urea = {
  fluido_id: 1, nombre: 'Urea', clave: 'urea', unidad: 'litros', envase: 'bin',
  sucursal_codigo: 'CAT', activo: true, orden: 1, capacidad: 1000, minimo: 200,
  saldo: 140, porcentaje: 14, envases: 1, abierto: 140, sellados: 0,
  ultima_entrada: '2026-09-01', ultima_salida: '2026-09-16',
  ultima_medicion: '2026-09-10', consumo_diario: 16, dias_restantes: 9,
  estado: 'aviso', usado: true, proveedor: 'Petrobras', proveedor_id: 1,
};
const aceite = {
  fluido_id: 2, nombre: 'Aceite 15W40', clave: 'aceite15w40', unidad: 'litros',
  envase: 'tambor', sucursal_codigo: null, activo: true, orden: 10, capacidad: 205,
  minimo: 41, saldo: 1602, porcentaje: 81.5, envases: 8, abierto: 167, sellados: 7,
  ultima_entrada: '2026-09-05', ultima_salida: '2026-09-17', ultima_medicion: null,
  consumo_diario: 4, dias_restantes: 400, estado: 'ok', usado: true,
  proveedor: 'Shell', proveedor_id: 2,
};
const grasa = {
  fluido_id: 3, nombre: 'Grasa', clave: 'grasa', unidad: 'kilos', envase: 'balde',
  sucursal_codigo: null, activo: true, orden: 30, capacidad: 20, minimo: 4,
  saldo: 0, porcentaje: 0, envases: 0, abierto: 0, sellados: 0,
  ultima_entrada: null, ultima_salida: null, ultima_medicion: null,
  consumo_diario: null, dias_restantes: null, estado: 'sin_cargar', usado: false,
  proveedor: null, proveedor_id: null,
};

const datos = (gestiona) => ({
  instalado: true,
  fluidos: [urea, aceite, grasa],
  proveedores: [{id: 1, nombre: 'Petrobras', rubros: ['urea'], activo: true, compras: 4},
                {id: 2, nombre: 'Shell', rubros: ['aceites', 'grasa'], activo: true, compras: 2}],
  movimientos: [
    {id: 3, fluido_id: 1, fluido: 'Urea', clave: 'urea', unidad: 'litros', envase: 'bin',
     tipo: 'salida', fecha: '2026-09-16', cantidad: 40, delta: -40, unidad_id: 1,
     patente: 'AD247MQ', interno: '2', km: 124000, proveedor: null, remito: null,
     importe: null, motivo: null, medido: null, usuario: 'Ramón', nota: null},
    {id: 2, fluido_id: 1, fluido: 'Urea', clave: 'urea', unidad: 'litros', envase: 'bin',
     tipo: 'ajuste', fecha: '2026-09-10', cantidad: -12, delta: -12, unidad_id: null,
     patente: null, interno: null, km: null, proveedor: null, remito: null,
     importe: null, motivo: 'Merma del mes', medido: 540, usuario: 'Nicolás', nota: null},
    {id: 1, fluido_id: 2, fluido: 'Aceite 15W40', clave: 'aceite15w40', unidad: 'litros',
     envase: 'tambor', tipo: 'entrada', fecha: '2026-09-05', cantidad: 1640, delta: 1640,
     unidad_id: null, patente: null, interno: null, km: null, proveedor: 'Shell',
     remito: 'A-77', importe: 3200000, motivo: null, medido: null,
     usuario: 'Nicolás', nota: null},
  ],
  por_unidad: [
    {mes: '2026-09-01', fluido_id: 1, fluido: 'Urea', clave: 'urea', unidad: 'litros',
     unidad_id: 1, patente: 'AD247MQ', interno: '2', sucursal: 'CAT', chofer: 'Ramón',
     despachos: 3, cantidad: 120, litros_gasoil: 3000, km: 9000,
     porcentaje_gasoil: 4, cada_100km: 1.33},
    {mes: '2026-09-01', fluido_id: 1, fluido: 'Urea', clave: 'urea', unidad: 'litros',
     unidad_id: 2, patente: 'AA823XJ', interno: '300', sucursal: 'COR', chofer: 'Ana',
     despachos: 2, cantidad: 90, litros_gasoil: 900, km: 2600,
     porcentaje_gasoil: 10, cada_100km: 3.46},
    {mes: '2026-09-01', fluido_id: 2, fluido: 'Aceite 15W40', clave: 'aceite15w40',
     unidad: 'litros', unidad_id: 1, patente: 'AD247MQ', interno: '2', sucursal: 'CAT',
     chofer: 'Ramón', despachos: 1, cantidad: 38, litros_gasoil: 3000, km: 9000,
     porcentaje_gasoil: 1.3, cada_100km: 0.42},
  ],
  banda_gasoil: [3, 6],
  envases: {bin: 'Bin', tambor: 'Tambor', tacho: 'Tacho', balde: 'Balde', tanque: 'Tanque'},
  rubros: ['combustible', 'urea', 'aceites', 'grasa', 'repuestos'],
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
      if (url.pathname === '/api/fluidos') {
        if (req.method() === 'GET') return route.fulfill({json: datos(gestiona)});
        pedidos.push(req.postDataJSON());
        return route.fulfill({json: {ok: true, saldo: 100,
                                     aviso: 'Quedan 100 litros. Hay que pedir Urea.'}});
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

    // El enlace viejo apuntaba a #urea: la urea ahora es un fluido más.
    await page.goto('http://taller.test/combustible#urea');
    await page.locator('.fluido').first().waitFor();
    assert.equal(await page.locator('.fluido').count(), 3);
    assert.equal(await page.locator('#page-title').innerText(), 'Fluidos');

    // El envase dibujado: la urea casi vacía, el aceite con siete sin abrir.
    const tarjetaUrea = await page.locator('[data-fluido="1"]').innerText();
    for (const x of ['140', 'HAY QUE PEDIR', '14% de un bin de 1.000'])
      assert(tarjetaUrea.includes(x), `falta "${x}" en la tarjeta: ${tarjetaUrea}`);
    assert((await page.locator('[data-fluido="2"] .sellados').innerText()).includes('+7'),
           'no dice cuántos envases quedan sin abrir');
    // El nivel del líquido es la altura del rectángulo dentro del envase.
    const alturas = await page.locator('.fluido svg g rect:first-child').evaluateAll(
      rects => rects.map(r => Math.round(Number(r.getAttribute('height')))));
    assert.deepEqual(alturas, [12, 68], 'el envase no se dibuja según lo que queda: ' + alturas);
    assert.equal(await page.locator('[data-fluido="3"] svg g rect').count(), 0,
                 'el que nunca se cargó no tiene nada adentro');
    assert((await page.locator('[data-fluido="3"]').innerText()).includes('SIN ESTRENAR'),
           'lo que nunca se compró no está vacío: está sin estrenar');
    assert((await page.locator('#u-resumen').innerText()).includes('Urea (140 litros)'),
           'el resumen tiene que decir qué hay que pedir');

    // La solapa no importa archivos: los fluidos se cargan a mano.
    assert.equal(await page.evaluate(() => getComputedStyle(
      document.querySelector('#imports')).display), 'none');

    // Los movimientos, con el signo puesto por el tipo.
    const filas = await page.locator('#u-movimientos tr').allInnerTexts();
    assert.equal(filas.length, 3);
    assert(filas[0].includes('-40'), 'el despacho no resta: ' + filas[0]);
    assert(filas[2].includes('+1.640'), 'la carga no suma: ' + filas[2]);
    assert(filas[1].includes('medido: 540'), 'la medición no muestra lo medido');

    // Elegir un fluido filtra sus movimientos y deja el resto a la vista.
    await page.click('[data-fluido="2"]');
    assert.equal(await page.locator('#u-movimientos tr').count(), 1);
    assert.equal(await page.locator('#u-titulo').innerText(), 'Movimientos de Aceite 15W40');

    // Despachar: el fluido elegido viene puesto y el km sale del maestro.
    await page.click('#u-despachar');
    assert.equal(await page.inputValue('#u-form-salida select[name="fluido_id"]'), '2',
                 'no vino puesto el fluido elegido');
    await page.fill('#u-form-salida input[name="cantidad"]', '38');
    await page.selectOption('#u-s-unidad', '1');
    assert.equal(await page.inputValue('#u-form-salida input[name="km"]'), '124500',
                 'no completó el km del maestro');
    await page.click('#u-form-salida button[type="submit"]');
    await page.waitForFunction(() => !document.querySelector('#u-aviso').hidden);
    const despacho = pedidos.find(p => p.op === 'despachar');
    assert.equal(despacho.cantidad, '38');
    assert.equal(despacho.fluido_id, '2');
    assert.equal(despacho.unidad_id, '1');
    assert((await page.locator('#u-aviso').innerText()).includes('Hay que pedir'));

    // Medir: se manda lo medido, no una corrección del saldo.
    await page.click('#u-medir');
    await page.fill('#u-form-medicion input[name="medido"]', '95');
    await page.fill('#u-form-medicion input[name="motivo"]', 'Merma');
    await page.click('#u-form-medicion button[type="submit"]');
    await page.waitForTimeout(200);
    const medicion = pedidos.find(p => p.op === 'medir');
    assert.equal(medicion.medido, '95');
    assert.equal(medicion.motivo, 'Merma');

    // Comprar: el proveedor sale de la lista, no de un texto libre.
    await page.click('#u-cargar');
    assert.deepEqual(
      await page.locator('#u-form-entrada select[name="proveedor_id"] option').allInnerTexts(),
      ['—', 'Petrobras', 'Shell']);

    // Por unidad: el % sobre gasoil es de la urea; fuera de 3–6% se marca.
    await page.click('[data-fluido="2"]');   // vuelve a mostrar todo
    const fuera = await page.locator('#u-unidades .fuera').allInnerTexts();
    assert.deepEqual(fuera, ['10%'], 'no marcó la unidad fuera de banda: ' + fuera);
    const filaAceite = await page.locator('#u-unidades tr', {hasText: 'Aceite'}).innerText();
    assert(filaAceite.includes('—'), 'el % sobre gasoil de un aceite no dice nada');

    // El que no gestiona despacha, pero no compra ni mide.
    gestiona = false;
    await page.reload();
    await page.locator('.fluido').first().waitFor();
    assert(await page.locator('#u-despachar').isVisible(), 'no puede despachar');
    assert(!await page.locator('#u-cargar').isVisible(), 'puede comprar sin gestionar');
    assert(!await page.locator('#u-medir').isVisible(), 'puede medir sin gestionar');
    assert.equal(await page.locator('[data-borrar-urea]').count(), 0,
                 'puede borrar movimientos sin gestionar');

    await page.setViewportSize({width: 390, height: 844});
    assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
           'la solapa de fluidos desborda a lo ancho en el celular');
    await page.screenshot({path: '/tmp/fluidos.png', fullPage: true});
    assert.deepEqual(errores, []);
    console.log('PASS: envases dibujados con lo que queda y los sellados al lado, sin ' +
                'estrenar distinto de vacío, signo por tipo, despacho con el fluido ' +
                'elegido y el km del maestro, medición por lo medido, proveedor de la ' +
                'lista, banda de urea y celular.');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
