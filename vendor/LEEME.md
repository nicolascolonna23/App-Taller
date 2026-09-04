# Lo que hay acá

Three.js **0.128.0**, tal como sale de npm, y dos de sus complementos:

| Archivo | Qué |
|---|---|
| `three.min.js` | el motor 3D |
| `OBJLoader.js` | lee los `.obj` de `modelos/` |
| `OrbitControls.js` | girar, acercar y mover con el mouse o el dedo |
| `FBXLoader.js` | lee los `.fbx`, que es como vienen la mayoría de los modelos |
| `fflate.min.js` | descomprime: el FBX binario viene comprimido |

Van en el repo y no en un CDN a propósito: el taller no siempre tiene buena
conexión, y una pantalla que depende de que Cloudflare conteste es una
pantalla que un día no abre. Son 780 KB que el navegador cachea una vez.

Licencia MIT (three.js). Para actualizarlos:

    npm pack three@<version>
    tar xzf three-<version>.tgz
    cp package/build/three.min.js                         vendor/
    cp package/examples/js/loaders/OBJLoader.js           vendor/
    cp package/examples/js/controls/OrbitControls.js      vendor/
    cp package/examples/js/loaders/FBXLoader.js           vendor/
    cp package/examples/js/libs/fflate.min.js             vendor/

Desde la 0.150 los complementos dejaron de publicarse como scripts sueltos
y pasaron a módulos ES: subir de versión no es copiar y pegar.
