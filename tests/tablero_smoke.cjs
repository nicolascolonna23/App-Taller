// Los dos tableros, cargados contra /api simuladas. Verifica que no quede
// nada de las planillas: ni una llamada a Google, ni un KPI sin fuente.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');

const RAIZ = path.join(__dirname, '..');
const flota = [
  { id:1, patente:'AH522SI', interno:'17', marca:'IVECO', modelo:'S-WAY 480', chofer:'CABRERA', sucursal:'LAD', uso:'LARGA DISTANCIA', semi:'' },
  { id:2, patente:'KOF186',  interno:'80', marca:'IVECO', modelo:'DAILY',     chofer:'PEREZ',   sucursal:'CAT', uso:'DISTRIBUCION LOCAL', semi:'' },
];
const services = [
  { patente:'AH522SI', sucursal:'LAD', plan_id:1, plan_nombre:'S-WAY', cada_km:45000,
    ultimo_fecha:'2026-06-15', ultimo_km:195997, proximo_km:240997, km_actual:239000, km_restantes:1997, estado:'urgente' },
  { patente:'KOF186', sucursal:'CAT', plan_id:2, plan_nombre:'FURGONES', cada_km:20000,
    ultimo_fecha:'2026-05-02', ultimo_km:80000, proximo_km:100000, km_actual:85000, km_restantes:15000, estado:'ok' },
];
const serie = {
  flota: [
    { mes:'2026-06-01', km:12400, litros:3680, unidades:2, litros_100km:29.68, litros_100km_lad:31.82 },
    { mes:'2026-07-01', km:13500, litros:4200, unidades:2, litros_100km:31.11, litros_100km_lad:33.33 },
  ],
  unidades: [
    { mes:'2026-06-01', patente:'AH522SI', sucursal:'LAD', marca:'IVECO', modelo:'S-WAY 480', chofer:'CABRERA', km:11000, litros:3500, litros_100km:31.82 },
    { mes:'2026-06-01', patente:'KOF186',  sucursal:'CAT', marca:'IVECO', modelo:'DAILY',     chofer:'PEREZ',   km:1400,  litros:180,  litros_100km:12.86 },
    { mes:'2026-07-01', patente:'AH522SI', sucursal:'LAD', marca:'IVECO', modelo:'S-WAY 480', chofer:'CABRERA', km:12000, litros:4000, litros_100km:33.33 },
    { mes:'2026-07-01', patente:'KOF186',  sucursal:'CAT', marca:'IVECO', modelo:'DAILY',     chofer:'PEREZ',   km:1500,  litros:200,  litros_100km:13.33 },
  ],
};

(async () => {
  const browser = await chromium.launch({ headless:true,
    ...(process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : {}) });
  try {
    const page = await browser.newPage({ viewport:{ width:1440, height:1000 } });
    const errores = [], externas = [];
    page.on('pageerror', e => errores.push(e.message));

    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (!/^(taller\.test|localhost)$/.test(url.hostname)) {
        // fonts.googleapis es decoracion; cualquier otra salida es una fuga.
        if (!/fonts\.(googleapis|gstatic)\.com$/.test(url.hostname)) externas.push(url.href);
        return route.abort();
      }
      const p = url.pathname;
      if (p === '/api/yo')     return route.fulfill({ json:{ nombre:'Prueba', rol:'admin' } });
      if (p === '/api/flota')  return route.fulfill({ json: flota });
      if (p === '/api/services') return route.fulfill({ json: services });
      if (p === '/api/combustible') {
        if (url.searchParams.get('vista') === 'serie') return route.fulfill({ json: serie });
        return route.fulfill({ json:{ meses:[], unidades:[] } });
      }
      if (p === '/api/mantenimiento') return route.fulfill({ json:{ planes:[], asignaciones:[], modelos:[] } });
      if (p === '/api/alertas') return route.fulfill({ json:{} });
      const archivo = { '/flota':'index.html', '/control':'control_flota.html' }[p]
                   || (p === '/sistema.css' ? 'sistema.css' : p === '/tema.js' ? 'tema.js' : null);
      if (archivo) return route.fulfill({ body: fs.readFileSync(path.join(RAIZ, archivo), 'utf8'),
                                          contentType: archivo.endsWith('.css') ? 'text/css'
                                                     : archivo.endsWith('.js') ? 'text/javascript' : 'text/html' });
      return route.fulfill({ status:404, body:'' });
    });

    // ---- /flota -------------------------------------------------------
    await page.goto('http://taller.test/flota');
    await page.locator('#kpis .kpi, #kpis > *').first().waitFor();
    // El CSS pone los titulos en mayusculas: se compara sin distinguir.
    const kpis = (await page.locator('#kpis').innerText()).toUpperCase();
    assert(kpis.includes('CONSUMO DEL MES'), 'falta el KPI de consumo');
    assert(kpis.includes('LITROS DEL MES'), 'falta el KPI de litros');
    for (const muerto of ['RALENTÍ', 'CO2', 'CO₂', 'PREFILTRO'])
      assert(!kpis.includes(muerto), `quedó el KPI "${muerto}"`);
    assert(kpis.includes('31,1') || kpis.includes('31.1'), 'el consumo no salió de la base: ' + kpis);
    assert.equal(await page.locator('#ch-co2, #ch-ralenti').count(), 0, 'quedaron gráficos sin fuente');
    assert.equal(await page.locator('#ch-consumo svg').count(), 1, 'no se dibujó el consumo');
    assert.equal((await page.locator('#fuente-txt').innerText()).toUpperCase(), 'DATOS EN VIVO');
    await page.screenshot({ path:'/tmp/flota.png', fullPage:true });

    // ---- /control -----------------------------------------------------
    await page.goto('http://taller.test/control');
    await page.locator('#kpis-globales').waitFor();
    await page.waitForFunction(() => document.querySelector('#flota-consumo svg'));
    const kg = (await page.locator('#kpis-globales').innerText()).toUpperCase();
    assert(kg.includes('CON CONSUMO CALCULADO'), 'falta el KPI de consumo calculado');
    assert.equal(await page.locator('#tab-prefiltro, #p-prefiltro').count(), 0, 'quedó la pestaña de prefiltros');
    assert.equal(await page.locator('#flota-co2, #rank-ralenti').count(), 0, 'quedaron tarjetas sin fuente');
    assert.equal(await page.locator('#rank-consumo svg').count(), 1, 'no se dibujó el ranking de consumo');
    const tabla = (await page.locator('#tbl-lad').innerText()).toUpperCase();
    assert(!tabla.includes('RALENTÍ'), 'quedó la columna de ralentí');
    assert(tabla.includes('L/100 KM'), 'falta la columna de consumo');
    await page.screenshot({ path:'/tmp/control.png', fullPage:true });

    // ---- ficha de una unidad ------------------------------------------
    await page.click('#tab-lad');            // la tabla vive en su pestaña
    await page.click('#tbl-lad button.pat');
    await page.waitForFunction(() => document.querySelector('#u-consumo svg'));
    const ficha = (await page.locator('#ficha').innerText()).toUpperCase();
    for (const muerto of ['RALENTÍ', 'CO₂', 'CO2', 'HORAS MOTOR'])
      assert(!ficha.includes(muerto), `la ficha todavía muestra "${muerto}"`);
    assert(ficha.includes('L/100 KM'), 'la ficha perdió el consumo');
    assert.equal(await page.locator('#u-co2, #u-ralenti').count(), 0, 'quedaron gráficos sin fuente en la ficha');
    assert.equal(await page.locator('#u-detalle thead th').count(), 4, 'el detalle mensual no quedó en 4 columnas');
    await page.screenshot({ path:'/tmp/ficha.png', fullPage:true });

    assert.deepEqual(externas, [], 'el tablero salió a buscar datos afuera: ' + externas.join(', '));
    assert.deepEqual(errores, [], 'errores de JS: ' + errores.join(' | '));
    console.log('PASS: los dos tableros cargan solo de /api, sin planillas, con el consumo calculado en la base.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
