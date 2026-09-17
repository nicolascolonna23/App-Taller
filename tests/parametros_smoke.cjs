// La pantalla de parámetros contra /api/parametros y /api/marcas simuladas.
// Verifica lo que la pantalla promete: que el kilometraje se elija entre
// dos opciones y no en un desplegable escondido, que un plan correctivo no
// pida intervalo ni un preventivo pida presupuesto, que el que solo
// gestiona pueda tocar los planes pero no los umbrales, y que la solapa de
// gomería muestre el logo de cada marca y no deje borrar una que se usa.
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

const marcas = () => ({
  marcas: [
    {id: 1, nombre: 'Fate', slug: 'fate', activa: true, logo_tipo: 'image/png',
     tiene_logo: true, cubiertas: 12},
    {id: 2, nombre: 'Kumho', slug: 'kumho', activa: false, logo_tipo: null,
     tiene_logo: false, cubiertas: 0},
  ],
  medidas: [
    {id: 1, medida: '295/80R22.5', corta: '295', clase: 'camion',
     descripcion: 'La de los camiones.', activa: true, orden: 1, cubiertas: 9},
    {id: 2, medida: '600x9', corta: '600', clase: 'autoelevador',
     descripcion: null, activa: true, orden: 10, cubiertas: 0},
  ],
  puede_gestionar: true,
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
      if (url.pathname === '/api/marcas') {
        if (req.method() === 'GET') return route.fulfill({json: marcas()});
        pedidos.push(req.postDataJSON());
        return route.fulfill({json: {ok: true}});
      }
      if (url.pathname.startsWith('/marcas/'))
        return route.fulfill({body: fs.readFileSync(path.join(dir, 'logo_diemar4.png')),
                              contentType: 'image/png'});
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

    // Gomería: el logo en lugar del nombre, y la marca que se usa no se borra.
    quien = 'admin';
    await page.reload();
    await page.locator('.opcion.on').waitFor();
    await page.click('[data-vista="gomeria"]');
    await page.locator('#marcas tr').first().waitFor();
    assert((await page.locator('#v-gomeria .modulo').innerText())
             .toLowerCase().includes('gomería'),
           'la solapa tiene que decir de qué módulo son estos parámetros');
    assert.equal(await page.locator('#marcas td .logo-marca img').count(), 2,
                 'cada marca se muestra con su logo');
    assert.equal(await page.locator('[data-borrar-marca="1"]').count(), 0,
                 'una marca con 12 cubiertas no se borra: se da de baja');
    assert.equal(await page.locator('[data-borrar-marca="2"]').count(), 1);
    assert((await page.locator('#marcas').innerText()).includes('de baja'),
           'tiene que verse cuál está de baja');

    // Editar carga el formulario con lo que hay, y guardar no manda logo vacío.
    await page.click('[data-marca="1"]');
    assert.equal(await page.inputValue('#m-nombre'), 'Fate');
    assert(await page.locator('#marca-sin-logo').isVisible(),
           'la marca con logo tiene que poder quedarse sin él');
    await page.uncheck('#m-activa');
    await page.click('#marca-form button[type="submit"]');
    await page.waitForTimeout(200);
    const marca = pedidos.find(p => p.op === 'guardar' && p.nombre === 'Fate');
    assert.equal(marca.id, 1);
    assert.equal(marca.activa, false);
    assert.equal(marca.logo, undefined, 'sin subir un logo nuevo no se manda ninguno');

    // Las medidas: la familia se elige, y el número que identifica es opcional.
    assert((await page.locator('#medidas').innerText()).includes('identifica: 295'));
    await page.click('#medida-nueva');
    await page.fill('#d-medida', '11R22.5');
    await page.selectOption('#d-clase', 'camion');
    await page.click('#medida-form button[type="submit"]');
    await page.waitForTimeout(200);
    const medida = pedidos.find(p => p.op === 'medida_guardar');
    assert.equal(medida.medida, '11R22.5');
    assert.equal(medida.clase, 'camion');

    await page.setViewportSize({width: 390, height: 844});
    assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
           'la pantalla de parámetros desborda a lo ancho en el celular');
    assert.deepEqual(errores, []);
    console.log('PASS: kilometraje en dos opciones con su estado, plan correctivo sin ' +
                'intervalo y preventivo sin presupuesto, asignación solo de preventivos, ' +
                'umbrales del que administra, marcas con logo que se dan de baja en vez ' +
                'de borrarse, medidas con su familia y celular.');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
