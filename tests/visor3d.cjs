/* Que ninguna goma quede gris cuando la unidad tiene mapa.

   El gris es «de esta rueda el mapa no sabe nada». Una unidad recién dada
   de alta a la que se le asignó una configuración sabe todo: sus gomas
   tienen que salir rojizas —sin cubiertas— igual que en cualquier otro
   modelo. En el semirremolque y en el autoelevador salían grises porque la
   pieza que abarca las dos ruedas de un eje no es de un lado ni del otro y
   no encontraba ninguna posición.

   Se prueban los siete modelos del repo, no dos: el que agregue el octavo
   se entera acá si su modelo no engancha con el mapa.

   BROWSER_PATH apunta al Chrome del que corre. En el contenedor es el
   Chromium de Playwright. */
const {chromium} = require('playwright');
const {spawn} = require('child_process');
const path = require('path'), assert = require('assert');
const raiz = path.resolve(__dirname, '..');

const MODELOS = [
  ['6x2', 'iveco-6x2.glb', 3],
  ['4x2', 'iveco-4x2.obj', 2],
  ['semi', 'trailer.obj', 3],
  ['autoelevador', 'forklift.fbx', 2],
  ['utilitario', 'utilitario.glb', 2],
  ['auto', 'auto.glb', 2],
  ['chasis', 'chasis.glb', 3],
];

(async () => {
  // Un servidor de archivos sobre el repo: el visor pide /modelos/... y
  // /vendor/... por dirección absoluta.
  const srv = spawn('python3', ['-m', 'http.server', '8731', '--bind', '127.0.0.1',
                                '--directory', raiz], {stdio: 'ignore'});
  await new Promise(r => setTimeout(r, 900));

  const browser = await chromium.launch({headless: true,
    executablePath: process.env.BROWSER_PATH || '/opt/pw-browsers/chromium',
    args: ['--enable-unsafe-swiftshader', '--no-sandbox']});
  let malas = 0;
  try {
    const page = await browser.newPage({viewport: {width: 1000, height: 700}});
    page.on('pageerror', e => { console.error('  error en la página:', e.message); malas++; });

    for (const [clave, archivo, ejes] of MODELOS) {
      await page.goto('http://127.0.0.1:8731/tests/visor3d.html',
                      {waitUntil: 'domcontentloaded'});
      const mapa = await page.evaluate(e => mapaDePrueba(e, 0), ejes);
      const r = await page.evaluate(([c, a, m]) => probar(c, a, m), [clave, archivo, mapa]);
      const colores = await page.evaluate(() => COLORES);

      assert.ok(r.ruedas > 0, `${archivo}: no se reconoció ninguna rueda`);
      const grises = r.colores.filter(c => c.color === colores.goma);
      console.log(`  ${archivo}: ${r.ruedas} piezas de rueda, ${r.ejes} ejes, ` +
                  `${grises.length} grises`);
      assert.strictEqual(grises.length, 0,
        `${archivo}: ${grises.length} de ${r.ruedas} piezas quedaron grises ` +
        `aunque la unidad tiene mapa (ejes del modelo: ${r.ejes})`);
      // Sin cubiertas puestas, todas tienen que decir lo mismo.
      const otros = [...new Set(r.colores.map(c => c.color))]
        .filter(c => c !== colores.falta);
      assert.deepStrictEqual(otros, [],
        `${archivo}: sin cubiertas montadas se esperaba solo ${colores.falta}, ` +
        `salieron también ${otros.join(', ')}`);
    }

    // Y con las cubiertas puestas, el azul: si el mapa no engancha, esto
    // pasaría igual que antes pintando todo del mismo color.
    await page.goto('http://127.0.0.1:8731/tests/visor3d.html',
                    {waitUntil: 'domcontentloaded'});
    const llena = await page.evaluate(() => mapaDePrueba(3, 6));
    const r = await page.evaluate(m => probar('semi', 'trailer.obj', m), llena);
    const colores = await page.evaluate(() => COLORES);
    assert.ok(r.colores.every(c => c.color === colores.puesta),
      'trailer.obj: con el mapa completo las gomas tienen que salir azules');
    console.log('  trailer.obj con el mapa completo: todas azules');
  } finally {
    await browser.close();
    srv.kill();
  }
  if (malas) { console.error(`${malas} errores en la página`); process.exit(1); }
  console.log('visor3d: OK');
})().catch(e => { console.error(e.message); process.exit(1); });
