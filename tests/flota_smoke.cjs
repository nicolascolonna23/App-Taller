// La pantalla de Flota: el chasis al lado de la patente y las dos salidas.
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
    const errores = []; page.on('pageerror', e => errores.push(e.message));
    let pedidoExcel = null;

    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      const p = url.pathname;
      if (p === '/api/yo') return route.fulfill({ json:{ nombre:'Prueba', rol:'admin' } });
      if (p === '/api/unidades/exportar') {
        pedidoExcel = url.searchParams.get('ids');
        return route.fulfill({ status:200, contentType:'application/octet-stream', body:'xlsx' });
      }
      if (p === '/api/unidades') return route.fulfill({ json:{
        unidades, sucursales:['LAD','CAT'], usos:['LARGA DISTANCIA','DISTRIBUCION LOCAL'],
        configuraciones:[], revisar:[], armados:[], planes_mantenimiento:[] } });
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
    const cab = await page.locator('#cabecera th').allInnerTexts();
    assert.equal(cab[0].trim().toUpperCase().replace(/\s*[▲▼]$/,''), 'PATENTE', 'la 1ª no es Patente: ' + cab[0]);
    assert.equal(cab[1].trim().toUpperCase().replace(/\s*[▲▼]$/,''), 'CHASIS', 'la 2ª no es Chasis: ' + cab[1]);
    assert.equal(cab.filter(t => /CHASIS/i.test(t)).length, 1, 'el chasis quedó dos veces');
    const fila1 = await page.locator('#cuerpo tr').first().locator('td').allInnerTexts();
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

    await page.screenshot({ path:'/tmp/flota-listado.png', fullPage:true });
    assert.deepEqual(errores, [], 'errores de JS: ' + errores.join(' | '));
    console.log('PASS: chasis 2ª columna; Excel y PDF exportan lo filtrado, con las bajas marcadas.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
