// La pantalla de usuarios y roles contra /api/usuarios simulada.
// Verifica lo que la pantalla promete: que el alta pida sucursal cuando el
// rol es de sucursal, que los módulos de un rol se marquen y se manden
// enteros, y que los roles de fábrica no ofrezcan borrarse.
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert');
const dir = path.resolve(__dirname, '..');

const datos = {
  usuarios: [
    {id: 1, usuario: 'nico', nombre: 'Nicolás Colonna', rol: 'admin',
     rol_nombre: 'Administrador', administra: true, activo: true,
     sucursal_codigo: null, ultimo_ingreso: '2026-09-15T12:00:00Z', sesiones: 1},
    {id: 2, usuario: 'marta', nombre: 'Marta Díaz', rol: 'sucursal',
     rol_nombre: 'Responsable de sucursal', administra: false, activo: true,
     sucursal_codigo: 'TUC', ultimo_ingreso: null, sesiones: 0},
    {id: 3, usuario: 'pedro', nombre: 'Pedro Luna', rol: 'operario',
     rol_nombre: 'Operario', administra: false, activo: false,
     sucursal_codigo: null, ultimo_ingreso: '2026-03-02T12:00:00Z', sesiones: 0},
  ],
  roles: [
    {codigo: 'admin', nombre: 'Administrador', descripcion: 'Todo, más usuarios.',
     gestiona: true, administra: true, pide_sucursal: false, de_sistema: true,
     activo: true, modulos: ['flota', 'ordenes', 'usuarios'], usuarios: 1},
    {codigo: 'sucursal', nombre: 'Responsable de sucursal',
     descripcion: 'Pide y rinde lo de su boca.', gestiona: false, administra: false,
     pide_sucursal: true, de_sistema: true, activo: true,
     modulos: ['solicitudes', 'alertas'], usuarios: 1},
    {codigo: 'operario', nombre: 'Operario', descripcion: 'Carga lo que hace.',
     gestiona: false, administra: false, pide_sucursal: false, de_sistema: true,
     activo: true, modulos: ['flota', 'ordenes'], usuarios: 1},
    {codigo: 'compras', nombre: 'Compras', descripcion: 'Mira el gasto.',
     gestiona: true, administra: false, pide_sucursal: false, de_sistema: false,
     activo: true, modulos: ['ordenes'], usuarios: 0},
  ],
  modulos: [
    {codigo: 'flota', nombre: 'Flota y services', ruta: '/flota', detalle: 'Panel general.'},
    {codigo: 'ordenes', nombre: 'Órdenes de trabajo', ruta: '/ordenes', detalle: 'El taller.'},
    {codigo: 'solicitudes', nombre: 'Solicitudes de orden de compra',
     ruta: '/solicitudes', detalle: 'El módulo de las sucursales.'},
    {codigo: 'alertas', nombre: 'Alertas', ruta: '/alertas', detalle: 'Lo de hoy.'},
    {codigo: 'usuarios', nombre: 'Usuarios y roles', ruta: '/usuarios', detalle: 'Esto.'},
  ],
  sucursales: [{codigo: 'CAT', nombre: 'Catamarca'}, {codigo: 'TUC', nombre: 'Tucumán'}],
  yo: 1,
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
      if (url.pathname === '/api/usuarios') {
        if (req.method() === 'GET') return route.fulfill({json: datos});
        pedidos.push(req.postDataJSON());
        return route.fulfill({json: {ok: true}});
      }
      if (url.pathname === '/api/yo')
        return route.fulfill({json: {nombre: 'Nicolás Colonna', rol: 'admin',
                                     rol_nombre: 'Administrador', administra: true,
                                     modulos: ['usuarios']}});
      if (url.pathname === '/logo.png')
        return route.fulfill({body: fs.readFileSync(path.join(dir, 'logo_diemar4.png')),
                              contentType: 'image/png'});
      if (url.pathname === '/usuarios')
        return route.fulfill({body: fs.readFileSync(path.join(dir, 'usuarios.html'), 'utf8'),
                              contentType: 'text/html'});
      return route.fulfill({status: 404, body: ''});
    });

    await page.goto('http://taller.test/usuarios');
    await page.locator('#filas tr').first().waitFor();
    assert.equal(await page.locator('#filas tr').count(), 3);
    await page.fill('#buscar', 'marta');
    assert.equal(await page.locator('#filas tr').count(), 1);
    await page.fill('#buscar', '');

    // El alta: un rol de sucursal pide sucursal, y el usuario no se elige solo.
    await page.click('#nuevoUsuario');
    await page.fill('#uUsuario', 'ana');
    await page.fill('#uNombre', 'Ana Ruiz');
    await page.selectOption('#uRol', 'sucursal');
    assert(await page.locator('#cajaSucursal').isVisible(),
           'el rol de sucursal tiene que pedir la sucursal');
    await page.selectOption('#uSucursal', 'CAT');
    await page.fill('#uClave', 'catamarca2026');
    await page.click('#guardarUsuario');
    const alta = pedidos.find(p => p.op === 'crear');
    assert.equal(alta.usuario, 'ana');
    assert.equal(alta.sucursal_codigo, 'CAT');
    assert.equal(alta.rol, 'sucursal');

    // Editar: el usuario no se cambia, el rol sí, y no se manda contraseña.
    await page.click('[data-editar="2"]');
    assert(await page.locator('#uUsuario').isDisabled(), 'el usuario no se cambia');
    assert(!await page.locator('#cajaClave').isVisible());
    await page.selectOption('#uRol', 'operario');
    await page.click('#guardarUsuario');
    const edicion = pedidos.find(p => p.op === 'guardar');
    assert.equal(edicion.id, 2);
    assert.equal(edicion.rol, 'operario');

    // Los roles: los de fábrica se editan, no se borran.
    await page.click('[data-vista="roles"]');
    await page.locator('#filasRoles tr').first().waitFor();
    assert.equal(await page.locator('#filasRoles tr').count(), 4);
    assert.equal(await page.locator('[data-borrar-rol]').count(), 1,
                 'solo el rol que no es de fábrica y no tiene gente ofrece borrarse');

    // Marcar módulos: la pantalla manda la lista entera, no el cambio.
    await page.click('[data-rol="sucursal"]');
    await page.locator('#rModulos input').first().waitFor();
    assert.equal(await page.locator('#rModulos input:checked').count(), 2);
    assert(await page.locator('#rSucursal').isChecked());
    await page.check('#rModulos input[value="flota"]');
    await page.click('#guardarRol');
    const rol = pedidos.find(p => p.op === 'guardar_rol');
    assert.equal(rol.codigo, 'sucursal');
    assert.deepEqual(rol.modulos.sort(), ['alertas', 'flota', 'solicitudes']);
    assert.equal(rol.pide_sucursal, true);

    // Un rol nuevo, desde cero.
    await page.click('#nuevoRol');
    await page.fill('#rCodigo', 'deposito');
    await page.fill('#rNombre', 'Depósito');
    await page.check('#rGestiona');
    await page.check('#rModulos input[value="ordenes"]');
    await page.click('#guardarRol');
    const nuevo = pedidos.filter(p => p.op === 'guardar_rol').at(-1);
    assert.equal(nuevo.codigo, 'deposito');
    assert.equal(nuevo.gestiona, true);
    assert.equal(nuevo.administra, false);
    assert.deepEqual(nuevo.modulos, ['ordenes']);

    await page.setViewportSize({width: 390, height: 844});
    assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
           'la pantalla de usuarios desborda a lo ancho en el celular');
    assert.deepEqual(errores, []);
    console.log('PASS: alta con sucursal según el rol, edición sin tocar el usuario, ' +
                'módulos marcados y mandados enteros, roles de fábrica sin borrar y celular.');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
