// El menú de la cuenta, que barra.js cuelga del nombre en todas las pantallas.
// Verifica lo que promete: que el nombre se toque, que adentro estén cambiar
// la contraseña y salir, que cambiarla pida la de ahora y que al lograrlo
// mande al login —porque al cambiarla se cierran todas las sesiones—.
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
const dir = path.resolve(__dirname, '..');

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_PATH ? {executablePath: process.env.BROWSER_PATH} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 900}});
    const errores = [], pedidos = [];
    let respuesta = {status: 200, json: {ok: true, cerro_sesiones: true}};
    page.on('pageerror', e => errores.push(e.message));
    await page.route('**/*', route => {
      const req = route.request(), url = new URL(req.url());
      if (url.pathname === '/api/clave') {
        pedidos.push(req.postDataJSON());
        return route.fulfill(respuesta);
      }
      if (url.pathname === '/api/yo')
        return route.fulfill({json: {nombre: 'Nicolás', usuario: 'nico', rol: 'admin',
                                     rol_nombre: 'Administrador', administra: true,
                                     modulos: ['parametros', 'usuarios']}});
      if (url.pathname === '/api/parametros')
        return route.fulfill({json: {instalado: true, parametros: {}, de_fabrica: {},
                                     planes: [], asignaciones: [], reglas: {},
                                     lecturas: {}, puede_gestionar: false,
                                     puede_administrar: false}});
      if (url.pathname === '/login')
        return route.fulfill({body: '<html><body>Login</body></html>',
                              contentType: 'text/html'});
      if (url.pathname === '/logo.png')
        return route.fulfill({body: fs.readFileSync(path.join(dir, 'logo_diemar4.png')),
                              contentType: 'image/png'});
      if (url.pathname === '/parametros')
        return route.fulfill({body: fs.readFileSync(path.join(dir, 'parametros.html'), 'utf8')
                                .replace('</head>', '<script src="/barra.js"></script></head>'),
                              contentType: 'text/html'});
      const archivo = path.join(dir, url.pathname.slice(1));
      if (fs.existsSync(archivo) && fs.statSync(archivo).isFile())
        return route.fulfill({path: archivo});
      return route.fulfill({status: 404, body: ''});
    });

    await page.goto('http://taller.test/parametros');
    await page.locator('[data-cuenta]').waitFor();

    // El nombre es un botón y adentro están las dos cosas de la cuenta.
    assert.equal(await page.locator('[data-cuenta]').getAttribute('role'), 'button');
    await page.click('[data-cuenta]');
    const menu = await page.locator('.menu-cuenta').innerText();
    for (const x of ['Nicolás', 'nico', 'Administrador', 'Cambiar contraseña', 'Cerrar sesión'])
      assert(menu.includes(x), `falta "${x}" en el menú de la cuenta: ${menu}`);
    assert.equal(await page.locator('.menu-cuenta a[href="/salir"]').count(), 1);
    // Y se cierra tocando afuera: un menú que queda abierto tapa la pantalla.
    await page.click('h1');
    assert.equal(await page.locator('.menu-cuenta').count(), 0);

    // Cambiar la contraseña: pide la de ahora y que las dos nuevas coincidan.
    await page.click('[data-cuenta]');
    await page.click('[data-clave]');
    await page.locator('.clave-caja').waitFor();
    await page.fill('#clave-actual', 'la-de-ahora');
    await page.fill('#clave-nueva', 'unaclavelarga1');
    await page.fill('#clave-repetir', 'otra-cosa');
    await page.click('.clave-caja [type=submit]');
    assert.equal(await page.locator('.clave-caja .mal').innerText(),
                 'Las dos nuevas no son iguales.');
    assert.equal(pedidos.length, 0, 'mandó al servidor algo que ya sabía que estaba mal');

    // Lo que contesta el servidor se muestra tal cual: es lo que explica qué pasó.
    respuesta = {status: 403, json: {error: 'La contraseña de ahora no es esa.'}};
    await page.fill('#clave-repetir', 'unaclavelarga1');
    await page.click('.clave-caja [type=submit]');
    await page.waitForFunction(() =>
      document.querySelector('.clave-caja .mal').textContent.includes('no es esa'));
    assert.deepEqual(pedidos.at(-1), {actual: 'la-de-ahora', nueva: 'unaclavelarga1'});

    // Y cuando sale bien, al login: cambiarla cierra todas las sesiones.
    respuesta = {status: 200, json: {ok: true, cerro_sesiones: true}};
    await page.click('.clave-caja [type=submit]');
    await page.waitForURL('**/login');

    assert.deepEqual(errores, []);
    console.log('PASS: el nombre abre la cuenta, con cambiar contraseña y salir; ' +
                'las dos nuevas tienen que coincidir, el error del servidor se ve, ' +
                'y al cambiarla se vuelve al login.');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
