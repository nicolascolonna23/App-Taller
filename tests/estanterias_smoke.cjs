// Estanterías del depósito de repuestos, contra /api/repuestos y
// /api/estanterias simuladas (con estado, para ver que lo guardado vuelve).
// Recorre lo que promete la pantalla: armar un pasillo de dos filas
// enfrentadas, mover una estantería en el plano, ubicar un repuesto
// arrastrándolo a un casillero con confirmación, moverlo por clic, y que
// cancelar no guarde nada.
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
const dir = path.resolve(__dirname, '..');

const arts = [
  {codigo: 'FIL-020', descripcion: 'Filtro de aceite', rubro: 'Filtros', interno: '20', anterior: '', minimo: 0, activo: true},
  {codigo: 'COR-007', descripcion: 'Correa poly-V', rubro: 'Motor', interno: '7', anterior: '', minimo: 0, activo: true},
  {codigo: 'LAM-001', descripcion: 'Lámpara H7', rubro: 'Electricidad', interno: '1', anterior: '', minimo: 0, activo: true},
];
const movs = [{id: 1, ts: 1, fecha: '2026-09-01', codigo: 'FIL-020', desc: 'Filtro de aceite',
               patente: '', tipo: 'Ajuste', cantidad: 12, costo: null, obs: ''}];

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_PATH ? {executablePath: process.env.BROWSER_PATH} : {})});
  try {
    const estado = {est: [], ubic: {}, sig: 1, posts: []};
    const page = await browser.newPage({viewport: {width: 1600, height: 1100}});
    const errores = [];
    page.on('pageerror', e => errores.push(e.message));
    page.on('dialog', d => d.accept());

    await page.route('**/*', async route => {
      const req = route.request(), url = new URL(req.url()), p = url.pathname;
      if (p === '/api/repuestos') return route.fulfill({json: {arts, movs, puede_gestionar: true}});
      if (p === '/api/estanterias' && req.method() === 'GET')
        return route.fulfill({json: {estanterias: estado.est, puede_gestionar: true,
          ubicaciones: Object.entries(estado.ubic).map(([codigo, u]) => ({codigo, ...u}))}});
      if (p === '/api/estanterias') {
        const d = req.postDataJSON(); estado.posts.push(d);
        if (d.op === 'estanterias_crear') {
          const ids = d.estanterias.map(e => { const id = estado.sig++; estado.est.push({...e, id}); return id; });
          return route.fulfill({json: {ids}});
        }
        if (d.op === 'estanteria_mover') {
          Object.assign(estado.est.find(e => e.id === d.id), {x_cm: d.x_cm, y_cm: d.y_cm, frente: d.frente});
          return route.fulfill({json: {ok: true}});
        }
        if (d.op === 'ubicar') {
          estado.ubic[d.codigo] = {estanteria_id: d.estanteria_id, piso: d.piso, modulo: d.modulo};
          return route.fulfill({json: {ok: true}});
        }
        return route.fulfill({status: 400, json: {error: 'op'}});
      }
      if (p.startsWith('/api/')) return route.fulfill({status: 503, json: {error: 'sin datos'}});
      if (p === '/repuestos') return route.fulfill({body: fs.readFileSync(path.join(dir, 'stock_repuestos.html'), 'utf8'), contentType: 'text/html'});
      const archivo = path.join(dir, p.slice(1));
      if (archivo.startsWith(dir + path.sep) && fs.existsSync(archivo) && fs.statSync(archivo).isFile())
        return route.fulfill({body: fs.readFileSync(archivo),
          contentType: p.endsWith('.js') ? 'text/javascript' : p.endsWith('.css') ? 'text/css' : 'image/png'});
      return route.abort();
    });

    await page.goto('http://taller.test/repuestos');
    await page.locator('table tbody tr').first().waitFor();
    await page.click('.tab[data-tab="estan"]');
    await page.locator('text=Sin estanterías').waitFor();

    // Un pasillo de dos filas de 3, enfrentadas.
    await page.click('[data-act="es-modo"][data-m="armar"]');
    await page.click('[data-act="es-pasillo"]');
    await page.fill('#pf-cant', '3');
    await page.locator('#pf-cant').dispatchEvent('input');
    assert.match(await page.textContent('#pf-res'), /6 estanterías: A1–A3 enfrentadas a A4–A6/);
    await page.click('[data-act="es-pas-si"]');
    await page.locator('#es-svg [data-es]').nth(5).waitFor();
    const creadas = estado.posts.find(x => x.op === 'estanterias_crear').estanterias;
    assert.equal(creadas.length, 6);
    assert.deepEqual(creadas.map(e => e.frente), ['sur', 'sur', 'sur', 'norte', 'norte', 'norte']);
    // La segunda fila queda del otro lado del pasillo: profundidad + ancho.
    assert.equal(creadas[3].y_cm - creadas[0].y_cm, 50 + 120);
    assert.match(await page.textContent('#es-svg'), /Pasillo A/);

    // Arrastrar A1 en el plano la mueve y se guarda la posición nueva.
    const a1 = page.locator('#es-svg [data-es="1"] .cu');
    const caja = await a1.boundingBox();
    await page.mouse.move(caja.x + 10, caja.y + 5);
    await page.mouse.down();
    await page.mouse.move(caja.x + 10, caja.y + 120, {steps: 8});
    await page.mouse.up();
    await page.waitForFunction(() => document.querySelector('.es-ficha .t') &&
                                     document.querySelector('.es-ficha .t').textContent.startsWith('A1'));
    const mov = estado.posts.find(x => x.op === 'estanteria_mover');
    assert.ok(mov && mov.id === 1 && mov.y_cm > creadas[0].y_cm, 'no se guardó el movimiento de A1');
    assert.equal(mov.y_cm % 25, 0, 'la posición no salta de a 25 cm');

    // Ubicar: arrastrar el filtro al piso 2, módulo 3 de A1.
    await page.click('[data-act="es-modo"][data-m="ubicar"]');
    await page.locator('.es-cas[data-piso="2"][data-mod="3"]').waitFor();
    await page.dragAndDrop('.es-item[data-cod="FIL-020"]', '.es-cas[data-piso="2"][data-mod="3"]');
    await page.locator('.modal h2', {hasText: 'Ubicar repuesto'}).waitFor();
    assert.match(await page.textContent('.modal'), /A1.*Piso 2 · Módulo 3/s);
    // Cancelar no guarda nada.
    await page.click('[data-act="es-conf-no"]');
    assert.ok(!estado.posts.some(x => x.op === 'ubicar'));
    await page.dragAndDrop('.es-item[data-cod="FIL-020"]', '.es-cas[data-piso="2"][data-mod="3"]');
    await page.click('[data-act="es-conf-si"]');
    await page.locator('.es-cas[data-piso="2"][data-mod="3"] .es-chip[data-cod="FIL-020"]').waitFor();
    assert.deepEqual(estado.ubic['FIL-020'], {estanteria_id: 1, piso: 2, modulo: 3});

    // Moverlo por clic: elegido en la lista, tocar otro casillero, confirmar.
    await page.click('.es-cas[data-piso="4"][data-mod="1"]');
    await page.locator('.modal h2', {hasText: 'Mover repuesto'}).waitFor();
    assert.match(await page.textContent('.modal'), /Ubicación actual/);
    await page.click('[data-act="es-conf-si"]');
    await page.locator('.es-cas[data-piso="4"][data-mod="1"] .es-chip').waitFor();
    assert.deepEqual(estado.ubic['FIL-020'], {estanteria_id: 1, piso: 4, modulo: 1});

    // Soltar sobre una estantería del plano pide el casillero.
    await page.dragAndDrop('.es-item[data-cod="COR-007"]', '#es-svg [data-es="5"] .cu');
    await page.locator('#cf-piso').waitFor();
    await page.selectOption('#cf-piso', '3');
    await page.click('[data-act="es-conf-si"]');
    await page.waitForFunction(() => document.querySelector('.es-ficha .t').textContent.startsWith('A5'));
    assert.deepEqual(estado.ubic['COR-007'], {estanteria_id: 5, piso: 3, modulo: 1});

    await page.click('.es-item[data-cod="FIL-020"]');
    await page.screenshot({path: path.join(process.env.CAPTURAS || '/tmp', 'estanterias_1600.png')});

    // La ubicación aparece en la tabla de repuestos.
    await page.click('.tab[data-tab="stock"]');
    assert.match(await page.textContent('table tbody'), /A1 · P4 · M1/);

    // Celular: las columnas se apilan y no hay desborde horizontal.
    await page.setViewportSize({width: 390, height: 900});
    await page.click('.tab[data-tab="estan"]');
    const ancho = await page.evaluate(() => document.documentElement.scrollWidth);
    assert.ok(ancho <= 392, 'desborde horizontal en 390 px: ' + ancho);

    await page.screenshot({path: path.join(process.env.CAPTURAS || '/tmp', 'estanterias_390.png'), fullPage: true});
    assert.deepEqual(errores, []);
    console.log('estanterías: ok');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
