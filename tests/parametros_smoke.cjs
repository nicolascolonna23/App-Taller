// La pantalla de parámetros contra /api/parametros simulada.
// Verifica lo que la pantalla promete: que el kilometraje se elija entre
// dos opciones y no en un desplegable escondido, que un plan correctivo no
// pida intervalo ni un preventivo pida presupuesto, y que el que solo
// gestiona pueda tocar los planes pero no los umbrales.
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
const dir = path.resolve(__dirname, '..');

const datos = (quien) => ({
  instalado: true,
  parametros: {km_origen: 'automatico', km_hora: '05:00'},
  planes: [
    {id: 1, nombre: 'Service M6', descripcion: null, clase: 'preventivo', cada_km: 20000,
     cada_dias: null, tareas: 'Aceite, filtros', horas_estimadas: null,
     costo_estimado: null, activo: true, unidades: 12},
    {id: 2, nombre: 'Cambio de embrague', descripcion: null, clase: 'correctivo',
     cada_km: null, cada_dias: null, tareas: null, horas_estimadas: 8,
     costo_estimado: 900000, activo: true, unidades: 0},
  ],
  asignaciones: [
    {unidad_id: 1, patente: 'AD247MQ', interno: '2', sucursal: 'CAT', plan_id: 1,
     plan_nombre: 'Service M6', cada_km: 20000, cada_dias: null},
    {unidad_id: 2, patente: 'AA823XJ', interno: '300', sucursal: 'COR', plan_id: null,
     plan_nombre: null, cada_km: null, cada_dias: null},
  ],
  reglas: {litros_maximos: 450, service_urgente_km: 5000, service_aviso_km: 15000,
           combustible_dias: 90},
  lecturas: {ayer: 47, ultima: '2026-09-17'},
  puede_gestionar: true,
  puede_administrar: quien === 'admin',
});

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_PATH ? {executablePath: process.env.BROWSER_PATH} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 1000}});
    const errores = [], pedidos = [];
    let quien = 'admin';
    page.on('pageerror', e => errores.push(e.message));
    await page.route('**/*', route => {
      const req = route.request(), url = new URL(req.url());
      if (url.pathname === '/api/parametros') {
        if (req.method() === 'GET') return route.fulfill({json: datos(quien)});
        pedidos.push(req.postDataJSON());
        return route.fulfill({json: {ok: true}});
      }
      if (url.pathname === '/api/yo')
        return route.fulfill({json: {nombre: 'Nicolás', rol: 'admin',
                                     rol_nombre: 'Administrador', administra: true,
                                     modulos: ['parametros', 'usuarios']}});
      if (url.pathname === '/logo.png')
        return route.fulfill({body: fs.readFileSync(path.join(dir, 'logo_diemar4.png')),
                              contentType: 'image/png'});
      if (url.pathname === '/parametros')
        return route.fulfill({body: fs.readFileSync(path.join(dir, 'parametros.html'), 'utf8'),
                              contentType: 'text/html'});
      return route.fulfill({status: 404, body: ''});
    });

    await page.goto('http://taller.test/parametros');
    await page.locator('.opcion.on').waitFor();

    // El kilometraje: dos opciones, la que rige marcada, y el estado real.
    assert.equal(await page.locator('.opcion.on').getAttribute('data-origen'), 'automatico');
    assert((await page.locator('#km-estado').innerText()).includes('47 lecturas'),
           'no dice si el automático está andando');
    await page.click('.opcion[data-origen="manual"]');
    await page.click('#km-guardar');
    await page.waitForTimeout(200);
    const km = pedidos.find(p => p.op === 'guardar');
    assert.equal(km.km_origen, 'manual');

    // Los planes: el correctivo no pide intervalo, el preventivo no pide plata.
    await page.click('[data-vista="planes"]');
    assert.equal(await page.locator('#planes tr').count(), 2);
    const tabla = await page.locator('#planes').innerText();
    assert(tabla.includes('no se agenda'), 'el correctivo debería decir que no se agenda');
    assert(tabla.includes('20.000 km'), 'falta el intervalo del preventivo');

    await page.click('#plan-nuevo');
    assert(await page.locator('#p-km').isVisible(), 'el preventivo tiene que pedir km');
    assert(!await page.locator('#p-costo').isVisible(), 'el preventivo no pide costo');
    await page.selectOption('#p-clase', 'correctivo');
    assert(!await page.locator('#p-km').isVisible(), 'el correctivo no lleva intervalo');
    assert(await page.locator('#p-costo').isVisible(), 'el correctivo pide costo estimado');
    await page.fill('#p-nombre', 'Bomba de agua');
    await page.fill('#p-horas', '4');
    await page.fill('#p-costo', '250000');
    await page.click('#plan-form button[type="submit"]');
    await page.waitForTimeout(200);
    const plan = pedidos.find(p => p.op === 'plan_guardar');
    assert.equal(plan.clase, 'correctivo');
    assert.equal(plan.horas_estimadas, '4');

    // La asignación ofrece solo preventivos: el correctivo no es una agenda.
    const opciones = await page.locator('[data-asignar="1"] option').allInnerTexts();
    assert.deepEqual(opciones, ['Sin plan', 'Service M6'],
                     'la asignación no debería ofrecer el correctivo: ' + opciones);
    await page.selectOption('[data-asignar="2"]', {label: 'Service M6'});
    await page.waitForTimeout(200);
    const asignar = pedidos.find(p => p.op === 'asignar');
    assert.equal(asignar.unidad_id, '2');

    // Los umbrales son del que administra; los planes, del que gestiona.
    quien = 'taller';
    await page.reload();
    await page.locator('.opcion.on').waitFor();
    assert(!await page.locator('#km-guardar').isEnabled(),
           'el que no administra no cambia de dónde salen los km');
    assert(await page.locator('#plan-nuevo').isEnabled(),
           'el responsable de taller sí parametriza los planes');

    await page.setViewportSize({width: 390, height: 844});
    assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
           'la pantalla de parámetros desborda a lo ancho en el celular');
    assert.deepEqual(errores, []);
    console.log('PASS: kilometraje en dos opciones con su estado, plan correctivo sin ' +
                'intervalo y preventivo sin presupuesto, asignación solo de preventivos, ' +
                'umbrales del que administra y celular.');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
