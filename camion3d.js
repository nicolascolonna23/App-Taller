/* =====================================================================
   EL CAMIÓN EN 3D — compartido entre Flota y Gomería
   ---------------------------------------------------------------------
   Vive acá y no adentro de una pantalla porque lo usan dos: la ficha de
   la unidad en Flota y el mapa de cubiertas en Gomería. Tener el mismo
   visor dos veces era garantía de que uno de los dos se quedara viejo.

   Lo que la pantalla tiene que poner:

     - Cuatro elementos: #visor (donde va el dibujo), #visor-rotulo,
       #visor-pista y #visor-vacio (el cartel de cuando no hay modelo).
     - Dos funciones: posicionesDe(esquina), que devuelve las posiciones
       del mapa de esa rueda, y elegirEsquina(esquina), que es lo que
       pasa cuando se toca una.

   Y llama a armarVisor(clave, archivo, opciones). Lo demás es de acá.
   ===================================================================== */

/* Los propios, con nombre propio: las pantallas ya tienen un $ y un esc
   y dos declaraciones del mismo nombre en el mismo alcance no arrancan. */
const nodo = s => document.querySelector(s);
const escHtml = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));

/* Los nombres del modelo propio, que sí sabemos cuáles son. Cualquier otro
   archivo cae en la búsqueda de más abajo. */
const RUEDAS = {
  rueda_frente_izq:1, rueda_frente_der:1, rueda_atras_izq:1, rueda_atras_der:1
};
/* Encontrar las ruedas sin depender de cómo las llamó el que armó el
   modelo. Los nombres cambian con cada archivo —en alemán, en inglés, o
   "Object_012"— así que primero se prueba por nombre y, si no da, se
   buscan por dónde están: son los pedazos de abajo, corridos hacia los
   costados, y todos parecidos entre sí.

   Devuelve el mismo objeto {eje, lado} que la tabla de nombres, así el
   resto de la pantalla no se entera de cómo se encontraron. */
/* Qué pedazos del modelo son ruedas. Sirven para dos cosas: para pintarlas
   y para saber a qué hay que apuntarle con el clic.

   Se buscan por nombre en varios idiomas —los modelos vienen de donde
   vienen— y, si eso no da, por dónde están: los pedazos de abajo, redondos
   y de un tamaño razonable. */
const PALABRAS_RUEDA = /rueda|wheel|tire|tyre|llanta|neumat|goma|kerek|gumi|\brad\b|roue|pneu/i;
/* La otra convención: FL, FR, ML, MR, RL, RR — front/middle/rear por
   left/right. Vienen así los modelos armados para juegos. */
const SIGLA_RUEDA = /^[fmr][lr]$/i;
/* Los colliders son cajas invisibles para las físicas del juego del que
   salió el modelo. Se dibujan como bloques blancos y desvirtúan todas las
   medidas, así que no entran.

   Acá van nombres y nada más. Las luces y las cámaras de verdad se sacan
   por lo que son, no por cómo se llaman: filtrarlas por nombre escondía
   los faros y los focos traseros del 6x2 —"Lights_head", "Rear_Lights"—
   que son chapa y vidrio, no una luz. */
const SOBRA = /collider|collision|bound(ing)?box|_col\b/i;

/* El nombre de una malla no siempre dice nada —en los glTF las mallas se
   llaman todas "model"— pero el del nodo que la contiene sí. Se mira la
   malla y sus padres. */
function nombresDe(m){
  const nombres = [];
  for (let o = m; o; o = o.parent) if (o.name) nombres.push(o.name);
  return nombres;
}

function esSobra(m){
  return nombresDe(m).some(n => SOBRA.test(n));
}

/* La caja de lo que se ve, sin colliders ni ayudas invisibles.

   Box3.setFromObject mete todo lo que cuelgue del objeto, mire o no mire:
   un collider que abarca el camión entero le duplica el tamaño y le corre
   el centro, y después todo lo demás sale mal. */
function cajaVisible(objeto){
  const caja = new THREE.Box3();
  objeto.traverse(m => {
    if (m.isMesh && m.geometry && !esSobra(m))
      caja.union(new THREE.Box3().setFromObject(m));
  });
  return caja.isEmpty() ? new THREE.Box3().setFromObject(objeto) : caja;
}

function ruedasDelModelo(objeto){
  const piezas = [];
  objeto.traverse(m => {
    if (!m.isMesh || !m.geometry || esSobra(m)) return;
    const c = new THREE.Box3().setFromObject(m);
    piezas.push({ malla:m, tam:c.getSize(new THREE.Vector3()),
                  centro:c.getCenter(new THREE.Vector3()) });
  });
  if (!piezas.length) return [];

  const porNombre = piezas.filter(p => nombresDe(p.malla).some(
    n => PALABRAS_RUEDA.test(n) || SIGLA_RUEDA.test(n)));
  if (porNombre.length) return porNombre.map(p => p.malla);

  const todo = new THREE.Box3().setFromObject(objeto);
  const tamTodo = todo.getSize(new THREE.Vector3());
  /* Primero, la rueda entera en una sola pieza, que es lo normal. */
  const sueltas = piezas.filter(p => {
    /* Abajo: una rueda no llega ni a la mitad del alto del camión. */
    if (p.centro.y > todo.min.y + tamTodo.y * 0.42) return false;
    /* Redonda de perfil: alto y largo parecidos. */
    const alto = p.tam.y, largo = p.tam.z;
    if (alto <= 0 || largo <= 0) return false;
    if (Math.abs(alto - largo) / Math.max(alto, largo) > 0.4) return false;
    /* De un tamaño razonable, ni un tornillo ni el chasis entero. */
    return alto > tamTodo.y * 0.12 && alto < tamTodo.y * 0.55;
  });

  /* Y que tenga su par del otro lado. Una goma nunca va sola ni en el eje
     del medio del vehículo: siempre hay otra igual, a la misma altura y a
     la misma distancia del centro, del lado contrario.

     Es lo que separa una rueda del contrapeso de un autoelevador, que es
     redondo de perfil, está abajo y mide lo mismo que una goma —pasa
     todos los filtros de arriba— pero está en el medio y no tiene par. */
  const conPar = sueltas.filter(p => sueltas.some(o => o !== p &&
    Math.abs(p.centro.x + o.centro.x) < tamTodo.x * 0.12 &&
    Math.abs(p.centro.x) > tamTodo.x * 0.12 &&
    Math.abs(p.centro.z - o.centro.z) < tamTodo.z * 0.06 &&
    Math.abs(p.tam.y - o.tam.y) < Math.max(p.tam.y, o.tam.y) * 0.25
  )).map(p => p.malla);

  return conPar.length >= 2 ? conPar : ruedasHechasPedazos(piezas, todo, tamTodo);
}

/* El otro caso: la rueda no es una pieza, son cientos.

   Hay modelos —los que salen de Blockbench, por ejemplo— donde cada goma
   viene partida en doscientos pedacitos de dos centímetros. Ninguno pasa
   por rueda mirándolo solo, y buscar pieza por pieza no encuentra nada.

   Lo que sí se ve es esto: las gomas son lo único que toca el piso. Se
   toma la franja de abajo de todo, se la corta en grupos a lo largo del
   camión —cada grupo es un eje— y de ahí se sube: cada pedazo que caiga
   dentro del círculo de la rueda es parte de la rueda.

   El radio sale de la huella. Un círculo cortado a la altura h deja una
   cuerda c, y de esas dos medidas sale el radio; no hace falta suponer
   cuánto mide una goma ni en qué escala vino el modelo. */
function ruedasHechasPedazos(piezas, todo, tamTodo){
  const piso = todo.min.y;
  /* La franja tiene que ser fina: si se hace alta entra el chasis y los
     tres ejes se pegan en un solo grupo. */
  const franja = tamTodo.y * 0.06;
  const tocan = piezas.filter(p => p.malla.geometry &&
    new THREE.Box3().setFromObject(p.malla).min.y < piso + franja);
  if (tocan.length < 2) return [];

  /* A lo largo del camión: cada montón es un eje. */
  const orden = tocan.slice().sort((a, b) => a.centro.z - b.centro.z);
  const grupos = [[orden[0]]];
  for (let i = 1; i < orden.length; i++) {
    if (orden[i].centro.z - orden[i - 1].centro.z > tamTodo.z * 0.03) grupos.push([]);
    grupos[grupos.length - 1].push(orden[i]);
  }

  const ruedas = new Set();
  let numero = 0;
  for (const g of grupos) {
    const caja = new THREE.Box3();
    for (const p of g) caja.union(new THREE.Box3().setFromObject(p.malla));
    /* Una rueda no va en el medio del camión: la pata de apoyo y el
       perno del enganche sí, y no son ruedas. */
    if (caja.max.x - caja.min.x < tamTodo.x * 0.5) continue;
    const cuerda = caja.max.z - caja.min.z;
    const radio = (cuerda * cuerda / 4 + franja * franja) / (2 * franja);
    if (!(radio > franja) || radio > tamTodo.y * 0.6) continue;

    /* El centro de la rueda, y todo lo que le entre adentro. Se mira de
       perfil —a lo alto y a lo largo— porque el ancho es el de la goma y
       no dice nada. */
    const cz = (caja.min.z + caja.max.z) / 2, cy = piso + radio;
    numero++;
    for (const p of piezas) {
      const dz = p.centro.z - cz, dy = p.centro.y - cy;
      if (dz * dz + dy * dy > radio * radio * 1.1) continue;
      /* De qué eje es este pedazo. Se anota acá, que es donde se sabe:
         más adelante los pedazos de dos ejes vecinos se tocan —una goma
         mide más que lo que hay entre eje y eje— y separarlos otra vez
         mirando dónde caen ya no se puede. */
      p.malla.userData.grupoEje = numero;
      ruedas.add(p.malla);
    }
  }
  return [...ruedas];
}

/* El color de fondo del recuadro, como lo dejó el tema. Sirve para que el
   piso del dibujo sea del mismo color que la pantalla y el camión no
   quede flotando sobre un agujero negro. */
function colorDeLaCaja(caja){
  const c = new THREE.Color(0x161b20);
  try {
    let el = caja;
    while (el) {
      const fondo = getComputedStyle(el).backgroundColor;
      /* Se sube hasta encontrar uno que pinte de verdad: los recuadros
         suelen ser transparentes y heredan del panel de atrás. */
      if (fondo && !/rgba\(0, 0, 0, 0\)|transparent/.test(fondo)) {
        c.set(fondo);
        break;
      }
      el = el.parentElement;
    }
  } catch (e) { /* si el navegador no lo dice, queda el oscuro de siempre */ }
  return c;
}

/* Cuando el modelo vino como una sola malla, partirlo en sus pedazos.

   Un archivo puede traer el camión entero en una malla sola, sin objetos
   adentro: no es que le falten las ruedas, es que están soldadas al resto
   en el mismo montón de triángulos. Pero soldadas de nombre nada más —la
   goma no comparte un solo vértice con el guardabarros—, así que se las
   puede separar.

   Se agrupan los triángulos que se tocan: dos que comparten un vértice son
   de la misma pieza. Lo que queda es lo que el que armó el modelo dibujó
   como piezas, y de ahí para abajo todo sigue igual que siempre. */
function partirSiEsUnaSola(raiz){
  const mallas = [];
  raiz.traverse(m => { if (m.isMesh && m.geometry) mallas.push(m); });
  /* Con dos o más piezas ya hay con qué trabajar. Y una malla gigante no
     se toca: partirla cuesta más de lo que rinde. */
  if (mallas.length > 2) return;
  for (const m of mallas) {
    if (m.geometry.attributes.position.count > 300000) continue;
    const partes = pedazosDe(m.geometry);
    if (partes.length < 4) continue;          /* no había nada que partir */
    const grupo = new THREE.Group();
    grupo.name = m.name || 'partido';
    for (let i = 0; i < partes.length; i++) {
      const hijo = new THREE.Mesh(partes[i], m.material);
      hijo.name = `${grupo.name}_${i + 1}`;
      grupo.add(hijo);
    }
    grupo.applyMatrix4(m.matrix);
    m.parent.add(grupo);
    m.parent.remove(m);
  }
  raiz.updateMatrixWorld(true);
}

/* Las islas de una geometría: los triángulos que se tocan entre sí.

   Dos vértices en el mismo punto son el mismo punto aunque el archivo los
   repita —los .fbx y los .obj repiten los vértices de cada cara— así que
   primero se sueldan por posición y recién después se agrupa. */
function pedazosDe(geo){
  const pos = geo.attributes.position, n = pos.count;
  const padre = new Int32Array(n);
  for (let i = 0; i < n; i++) padre[i] = i;
  const raiz = x => { while (padre[x] !== x) { padre[x] = padre[padre[x]]; x = padre[x]; } return x; };
  const une = (a, b) => { a = raiz(a); b = raiz(b); if (a !== b) padre[b] = a; };

  const visto = new Map();
  for (let i = 0; i < n; i++) {
    const k = pos.getX(i).toFixed(4) + ',' + pos.getY(i).toFixed(4) + ',' +
              pos.getZ(i).toFixed(4);
    const antes = visto.get(k);
    if (antes === undefined) visto.set(k, i); else une(antes, i);
  }

  const idx = geo.index, cuantos = idx ? idx.count : n;
  const v = i => idx ? idx.getX(i) : i;
  for (let i = 0; i + 2 < cuantos; i += 3) { une(v(i), v(i + 1)); une(v(i), v(i + 2)); }

  const islas = new Map();
  for (let i = 0; i + 2 < cuantos; i += 3) {
    const r = raiz(v(i));
    if (!islas.has(r)) islas.set(r, []);
    islas.get(r).push(i);
  }
  if (islas.size < 4) return [];

  /* Una geometría por isla, copiando los atributos que traía. */
  const atributos = ['position', 'normal', 'uv'].filter(a => geo.attributes[a]);
  return [...islas.values()].map(tris => {
    const nueva = new THREE.BufferGeometry();
    for (const nombre of atributos) {
      const a = geo.attributes[nombre], ancho = a.itemSize;
      const datos = new Float32Array(tris.length * 3 * ancho);
      let k = 0;
      for (const t of tris) for (let j = 0; j < 3; j++) {
        const i = v(t + j);
        for (let c = 0; c < ancho; c++) datos[k++] = a.array[i * ancho + c];
      }
      nueva.setAttribute(nombre, new THREE.BufferAttribute(datos, ancho));
    }
    if (!geo.attributes.normal) nueva.computeVertexNormals();
    return nueva;
  });
}

/* Los ejes del modelo, de adelante hacia atrás.

   Antes esto era un solo corte al medio: adelante y atrás. En un 4x2 da
   igual —hay dos ejes y nada más— pero un 6x2 tiene tres, y tocar una
   rueda trasera marcaba las cuatro de atrás. Un eje es un eje.

   Las ruedas de un mismo eje están a la misma altura del camión, y entre
   eje y eje hay más de un metro: se ordenan a lo largo y se corta donde
   haya un salto de más de media rueda. La medida sale de las ruedas
   mismas para que no dependa de la escala del modelo. */
function ejesDelModelo(ruedas){
  if (!ruedas.length) return [];
  const con = ruedas.map(m => {
    const c = new THREE.Box3().setFromObject(m);
    return { malla:m, caja:c, z:(c.min.z + c.max.z) / 2,
             largo:c.max.z - c.min.z };
  }).sort((a, b) => a.z - b.z);

  let ejes;
  if (con.every(r => r.malla.userData.grupoEje)) {
    /* Las ruedas hechas pedazos ya vienen agrupadas de cuando se las
       encontró. Cortar por dónde caen no serviría: los pedazos de dos
       ejes vecinos se superponen. */
    const por = new Map();
    for (const r of con) {
      const k = r.malla.userData.grupoEje;
      if (!por.has(k)) por.set(k, []);
      por.get(k).push(r);
    }
    ejes = [...por.values()].sort((a, b) => media(a) - media(b));
  } else {
    /* Una rueda por pieza: se ordenan a lo largo y se corta donde haya un
       salto de más de media rueda. La medida sale de las ruedas mismas
       para que no dependa de la escala del modelo. */
    const salto = Math.max(...con.map(r => r.largo)) * 0.5 || 0.3;
    ejes = [[con[0]]];
    for (let i = 1; i < con.length; i++) {
      if (con[i].z - con[i - 1].z > salto) ejes.push([]);
      ejes[ejes.length - 1].push(con[i]);
    }
  }

  /* Cada rueda se queda con su eje y su lado: después alcanza con mirarla
     para saber cuál es, sin volver a medir nada. Con un modelo de dos mil
     pedazos eso es la diferencia entre pintar al toque y trabarse. */
  return ejes.map((grupo, i) => {
    for (const r of grupo) {
      r.malla.userData.eje = i + 1;
      r.malla.userData.lado =
        r.caja.max.x < 0 ? 'I' : r.caja.min.x > 0 ? 'D' : 'ambos';
    }
    return { numero:i + 1, z: media(grupo) };
  });
}

const media = g => g.reduce((a, r) => a + r.z, 0) / g.length;

/* Cómo se llama cada eje, para el rótulo del panel. */
function nombreDelEje(eje, cuantos){
  if (eje === 1) return 'delantera';
  if (eje === cuantos) return 'trasera';
  if (cuantos === 3) return 'del medio';
  return `del ${eje}.º eje`;
}

function esquina(eje, lado){
  return { eje, lado,
           rotulo: nombreDelEje(eje, V.ejes.length) + ' ' +
                   (lado === 'I' ? 'izquierda' : 'derecha') };
}

/* Dónde se tocó, convertido en rueda del camión.

   Se usa el punto del clic y no la malla porque hay modelos que traen las
   dos ruedas de un eje en una sola pieza: preguntarle a la malla de qué
   lado está no tiene respuesta, preguntarle al dedo sí. El eje sí sale de
   la malla, que es de uno solo siempre. */
function esquinaDelPunto(punto, malla){
  const lado = punto.x < 0 ? 'I' : 'D';
  const eje = (malla && malla.userData.eje) || ejeMasCerca(punto.z);
  return esquina(eje, lado);
}

function ejeMasCerca(z){
  if (!V.ejes.length) return 1;
  return V.ejes.reduce((a, b) =>
    Math.abs(b.z - z) < Math.abs(a.z - z) ? b : a).numero;
}

/* Lo que la pantalla le pasó al armar el visor. */
let VISOR = {};

const V = { escena:null, camara:null, render:null, control:null, ruedas:[],
            anim:null, modelo:null, esquina:null, ejes:[] };

function apagarVisor(){
  if (V.anim) cancelAnimationFrame(V.anim);
  V.anim = null;
  if (V.render){ V.render.forceContextLoss(); V.render.dispose();
    V.render.domElement.remove(); }
  Object.assign(V, { escena:null, camara:null, render:null, control:null,
                     ruedas:[], modelo:null, esquina:null, ejes:[] });
}

function visorVacio(texto){
  apagarVisor();
  nodo('#visor-vacio').hidden = false;
  nodo('#visor-vacio').innerHTML = texto;
  nodo('#visor-pista').textContent = '';
  nodo('#visor-rotulo').textContent = '';
}

/* clave: '4x2', '6x2' o 'semi'.  archivo: el nombre del modelo.
   opciones.por: de dónde salió la elección, para el rótulo.
   opciones.version: para que el navegador no use una copia vieja. */
function armarVisor(clave, archivo, opciones){
  apagarVisor();
  VISOR = opciones || {};
  nodo('#visor-vacio').hidden = true;
  const POR = { mano:'elegido a mano', mapa:'por el mapa de cubiertas',
                modelo:'lo dice el modelo', codigo:'por el código de Iveco',
                equipo:'está cargado como equipo',
                'no se sabe':'sin datos' };
  const NOMBRE = { '6x2':'Tractor 6x2 / 6x4', '4x2':'Tractor 4x2',
                   semi:'Semirremolque', autoelevador:'Autoelevador' };
  nodo('#visor-rotulo').textContent =
    (NOMBRE[clave] || clave) + (POR[VISOR.por] ? ' · ' + POR[VISOR.por] : '');
  nodo('#visor-pista').textContent = 'Arrastrá para girar · tocá una rueda';

  const caja = nodo('#visor');
  const esc3 = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(38, caja.clientWidth / caja.clientHeight, .1, 200);
  cam.position.set(7.5, 3.4, 7.5);

  const ren = new THREE.WebGLRenderer({ antialias:true, alpha:true });
  ren.setPixelRatio(Math.min(devicePixelRatio, 2));
  ren.setSize(caja.clientWidth, caja.clientHeight);
  caja.appendChild(ren.domElement);

  /* El piso y el rebote siguen al tema de la pantalla: en claro un piso
     negro debajo del camión se ve como un agujero. El color sale del
     recuadro del visor, que ya está pintado por el tema. */
  const suelo = colorDeLaCaja(caja);
  const claro = suelo.r + suelo.g + suelo.b > 1.5;

  /* Sobre piso claro la carrocería se baja un punto: un camión blanco
     sobre fondo blanco no se ve. */
  const blanco = new THREE.MeshStandardMaterial(
    { color: claro ? 0xdde3e8 : 0xf2f4f6, roughness:.42, metalness:.12 });

  /* Luz de tarde: una clave alta y un relleno bajo del otro lado, para que
     el blanco de la carrocería no se aplane. */
  esc3.add(new THREE.HemisphereLight(0xdfe8f2, claro ? 0xc9d2da : 0x0b0f13, .95));
  const sol = new THREE.DirectionalLight(0xfff2e2, 1.35);
  sol.position.set(6, 9, 5); esc3.add(sol);
  const relleno = new THREE.DirectionalLight(0x9fc4ef, .45);
  relleno.position.set(-7, 3, -5); esc3.add(relleno);

  const ctrl = new THREE.OrbitControls(cam, ren.domElement);
  ctrl.target.set(0, 1.5, 0);
  ctrl.enableDamping = true; ctrl.dampingFactor = .08;
  ctrl.minDistance = 5; ctrl.maxDistance = 22;
  /* Que no se pueda mirar desde abajo del piso: se ve el interior hueco. */
  ctrl.maxPolarAngle = Math.PI / 2 - .04;
  ctrl.enablePan = false;

  const goma   = new THREE.MeshStandardMaterial({ color:0x24282d, roughness:.92, metalness:.02 });

  /* El .obj y el .fbx se leen igual de acá para abajo. El FBX se acepta
     porque es como vienen casi todos los modelos, y convertirlos sería un
     paso más que se puede saltear. */
  const ext = archivo.toLowerCase().split('.').pop();
  const ClaseCargador = ext === 'fbx' ? THREE.FBXLoader
                      : (ext === 'glb' || ext === 'gltf') ? THREE.GLTFLoader
                      : THREE.OBJLoader;
  if (!ClaseCargador){
    visorVacio(`Falta el lector para el archivo <code>${escHtml(archivo)}</code>. ` +
      'Recargá la página; si sigue igual, avisá al administrador.');
    return;
  }
  const cargador = new ClaseCargador();

  /* La versión evita que quede pegado en caché un modelo anterior —o el 404
     de antes de que se haya subido— cuando se reemplaza uno con el mismo
     nombre. */
  const version = VISOR.version || '';
  const urlModelo = '/modelos/' + encodeURIComponent(archivo) +
    (version ? '?v=' + encodeURIComponent(version) : '');

  cargador.load(urlModelo, cargado => {
    if (!V.render || V.render !== ren) return;      /* se cerró mientras cargaba */
    /* El GLTFLoader devuelve la escena adentro de un sobre; los otros dos
       devuelven el objeto pelado. */
    const obj = cargado.scene || cargado;

    /* Refrescar las matrices antes de medir nada. Box3.setFromObject no
       actualiza las de los padres, y en un glTF la posición de cada rueda
       vive en el nodo que la contiene, no en la malla: sin esto se leen
       todas en el origen y el enderezado gira un modelo que estaba bien. */
    obj.updateMatrixWorld(true);

    /* Los FBX traen adentro las luces y la cámara con las que los armaron.
       La escena ya tiene las suyas, y las de adentro le pegan de más al
       modelo: el piso queda blanco y la carrocería se aplana. */
    const aSacar = [];
    obj.traverse(o => { if (o.isLight || o.isCamera) aSacar.push(o); });
    for (const o of aSacar) o.parent && o.parent.remove(o);
    /* Los colliders se apagan antes de medir nada: son cajas que abarcan
       el camión entero y falsean el tamaño, el centro y el enderezado. */
    obj.traverse(o => { if (o.isMesh && esSobra(o)) o.visible = false; });

    /* Y hay modelos que vienen como una sola malla, todo soldado en un
       archivo: el autoelevador es uno. Ahí no hay ruedas que buscar
       porque no hay piezas. Se lo parte antes de mirar nada. */
    partirSiEsUnaSola(obj);

    /* Cada modelo viene como lo dejó su autor: en las unidades que sea,
       parado en Y o en Z, girado en cualquier ángulo y a veces hundido
       bajo el piso. En vez de pedir que vengan prolijos, se los acomoda.
       El orden importa: primero se lo para, después se lo endereza, y
       recién ahí se lo escala y se lo apoya. */
    let caja = cajaVisible(obj);
    let tam = caja.getSize(new THREE.Vector3());

    /* 1. Pararlo. El resto de la pantalla espera el alto en Y; si el lado
          más grande cayó ahí, el modelo viene parado en Z, que es como
          exporta media herramienta. */
    if (tam.y > tam.z * 1.15 && tam.y > tam.x * 1.15) {
      obj.rotation.x = -Math.PI / 2;
      obj.updateMatrixWorld(true);
    }

    /* 2. Enderezarlo. Los modelos vienen girados en cualquier ángulo, no
          solo en múltiplos de noventa grados: el 6x2 venía en diagonal, a
          cuarenta grados. La dirección de marcha no se puede sacar de la
          caja —un camión en diagonal tiene la caja casi cuadrada— pero sí
          de las ruedas: los ejes están alineados con el camión, siempre.

          Se saca el eje principal de los centros de las ruedas, que es la
          dirección en la que están más desparramadas. Tomar las dos ruedas
          más lejanas no sirve: en un camión bien orientado esas dos son la
          diagonal, y enderezar por ahí tuerce un modelo que ya estaba
          derecho. */
    let ruedas = ruedasDelModelo(obj);
    if (ruedas.length >= 2) {
      const puntos = ruedas.map(m =>
        new THREE.Box3().setFromObject(m).getCenter(new THREE.Vector3()));
      const n = puntos.length;
      const mx = puntos.reduce((a, p) => a + p.x, 0) / n;
      const mz = puntos.reduce((a, p) => a + p.z, 0) / n;
      let sxx = 0, szz = 0, sxz = 0;
      for (const p of puntos) {
        sxx += (p.x - mx) ** 2; szz += (p.z - mz) ** 2;
        sxz += (p.x - mx) * (p.z - mz);
      }
      /* El ángulo del eje principal de una nube de puntos en dos
         dimensiones sale directo de la matriz de covarianza. */
      const ang = 0.5 * Math.atan2(2 * sxz, sxx - szz);
      const dx = Math.cos(ang), dz = Math.sin(ang);
      /* Solo se endereza si el eje principal está de verdad torcido:
         girar por medio grado es ruido. */
      const giro = -Math.atan2(dx, dz);
      if (Math.abs(Math.sin(giro)) > 0.02) {
        obj.rotation.y += giro;
        obj.updateMatrixWorld(true);
        ruedas = ruedasDelModelo(obj);
      }

      /* Ya está a lo largo de Z, pero puede haber quedado de culata. De qué
         lado queda el frente depende de qué se está dibujando. */
      const cajaGiro = cajaVisible(obj);
      const medio = cajaGiro.getCenter(new THREE.Vector3()).z;
      let alReves;

      if (clave === 'autoelevador') {
        /* En un autoelevador el frente es donde está el mástil, y ahí van
           las ruedas grandes: son las que traccionan y las que aguantan la
           carga. Atrás van las chicas, las que doblan.

           La altura no sirve para decidirlo —el techo de protección va de
           punta a punta y tapa al mástil— pero el tamaño de las gomas no
           falla en ningún autoelevador. */
        const cajas = ruedas.map(m => new THREE.Box3().setFromObject(m));
        const grande = cajas.reduce((a, c) =>
          c.max.y - c.min.y > a.max.y - a.min.y ? c : a);
        alReves = (grande.min.z + grande.max.z) / 2 > medio;

      } else if (clave === 'semi') {
        /* Un semi es igual de alto de punta a punta, así que la altura no
           dice nada. Lo que sí: los ejes van todos atrás, y adelante no
           hay más que el perno de enganche. */
        const zr = ruedas.reduce((a, m) =>
          a + new THREE.Box3().setFromObject(m).getCenter(new THREE.Vector3()).z,
          0) / ruedas.length;
        alReves = zr < medio;
      } else {
        /* En un tractor el frente es donde está la cabina, que es la parte
           alta; atrás va el chasis pelado.

           Hay que mirar los vértices y no las cajas: la carrocería suele
           ser una sola malla que abarca el camión entero, y su caja no
           dice de qué lado está lo alto. Se toma uno de cada veinte, que
           para esto alcanza y sobra. */
        let altoAdelante = -Infinity, altoAtras = -Infinity;
        const v = new THREE.Vector3();
        obj.traverse(m => {
          if (!m.isMesh || !m.geometry || !m.geometry.attributes.position) return;
          if (esSobra(m)) return;
          const pos = m.geometry.attributes.position;
          for (let i = 0; i < pos.count; i += 20) {
            v.fromBufferAttribute(pos, i).applyMatrix4(m.matrixWorld);
            if (v.z < medio) altoAdelante = Math.max(altoAdelante, v.y);
            else altoAtras = Math.max(altoAtras, v.y);
          }
        });
        alReves = altoAtras > altoAdelante;
      }

      if (alReves) {
        obj.rotation.y += Math.PI;
        obj.updateMatrixWorld(true);
        ruedas = ruedasDelModelo(obj);
      }
    }

    caja = cajaVisible(obj);
    tam = caja.getSize(new THREE.Vector3());

    /* 3. Escalarlo. Un tractor mide seis metros y medio; si el modelo mide
          650 venía en centímetros, y si mide 0,065 en otra cosa. */
    const largo = Math.max(tam.x, tam.y, tam.z);
    if (largo > 0 && (largo < 1.5 || largo > 20)) {
      obj.scale.multiplyScalar(6.5 / largo);
      obj.updateMatrixWorld(true);
      caja = cajaVisible(obj);
      tam = caja.getSize(new THREE.Vector3());
    }

    /* Las del nombre exacto que usa el repo mandan; si no, las que se
       reconocieron para enderezarlo. */
    const porNombre = [];
    obj.traverse(m => { if (m.isMesh && RUEDAS[m.name]) porNombre.push(m); });
    const esRueda = new Set(porNombre.length >= 2 ? porNombre : ruedas);

    obj.traverse(m => {
      if (!m.isMesh) return;
      /* Los colliders se esconden en vez de borrarse: son parte del
         archivo y borrarlos podría romper la jerarquía. */
      if (esSobra(m)) { m.visible = false; return; }
      m.material = esRueda.has(m) ? goma.clone() : blanco;
      if (esRueda.has(m)) V.ruedas.push(m);
    });

    nodo('#visor-pista').textContent = V.ruedas.length
      ? 'Arrastrá para girar · tocá una rueda'
      : 'Arrastrá para girar · en este modelo no se reconocieron las ruedas';
    /* Centrado a lo largo y a lo ancho, y apoyado en el piso. */
    obj.position.x -= (caja.min.x + caja.max.x) / 2;
    obj.position.z -= (caja.min.z + caja.max.z) / 2;
    obj.position.y -= caja.min.y;
    obj.updateMatrixWorld(true);
    esc3.add(obj);
    const caja3 = cajaVisible(obj);

    /* Los ejes, de adelante hacia atrás. Va después de mover el modelo y no
       antes: calculado sobre las posiciones viejas queda corrido y todos
       los clics caen en el eje equivocado. */
    V.ejes = ejesDelModelo(V.ruedas);

    /* La cámara se acomoda al camión y no al revés: el S-Way y el Hi-Way
       no miden lo mismo, y el que venga después tampoco. */
    const medida = caja3.getSize(new THREE.Vector3());
    const mayor = Math.max(medida.x, medida.y, medida.z);
    /* La distancia a la que el camión entra justo en el encuadre, más un
       margen para poder girarlo sin que se salga. Hay que mirar los dos
       lados del cuadro y no solo el alto: la ficha es más ancha que alta,
       y encuadrar por el vertical deja el camión chiquito en el medio de
       un panel vacío. Se mira desde una esquina y un poco desde arriba,
       que es como se le ve el techo y las cuatro ruedas de una. */
    const medioV = (cam.fov * Math.PI / 180) / 2;
    const medioH = Math.atan(Math.tan(medioV) * Math.max(cam.aspect, .5));
    const lejos = Math.max(mayor / (2 * Math.tan(medioH)),
                           medida.y / (2 * Math.tan(medioV))) * 1.4;
    cam.position.copy(new THREE.Vector3(1, .42, 1).normalize().multiplyScalar(lejos));
    /* Al centro del camión, no al de la escena: si mira más abajo, el
       camión se va para arriba y queda medio panel de piso vacío. */
    ctrl.target.set(0, medida.y / 2, 0);
    ctrl.minDistance = lejos * .5;
    ctrl.maxDistance = lejos * 2.2;
    ctrl.update();
    V.modelo = obj;
    pintarRuedas();
  }, undefined, error => {
    const detalle = error && error.message ? ` (${escHtml(error.message)})` : '';
    visorVacio(`No se pudo cargar <code>${escHtml(archivo)}</code>${detalle}. ` +
      'Probá recargar la página.');
  });

  /* Piso: un disco apenas más claro, para que el camión no flote. */
  const piso = new THREE.Mesh(new THREE.CircleGeometry(9, 64),
    new THREE.MeshStandardMaterial({ color:suelo, roughness:1 }));
  piso.rotation.x = -Math.PI / 2; piso.position.y = -.01; esc3.add(piso);

  Object.assign(V, { escena:esc3, camara:cam, render:ren, control:ctrl });

  const raton = new THREE.Vector2(), rayo = new THREE.Raycaster();
  /* Devuelve dónde pegó el rayo, no qué malla: la esquina sale del punto. */
  const enRueda = ev => {
    const r = ren.domElement.getBoundingClientRect();
    const t = ev.changedTouches ? ev.changedTouches[0] : ev;
    raton.x = ((t.clientX - r.left) / r.width) * 2 - 1;
    raton.y = -((t.clientY - r.top) / r.height) * 2 + 1;
    rayo.setFromCamera(raton, cam);
    const dio = rayo.intersectObjects(V.ruedas, false);
    return dio.length ? dio[0] : null;
  };
  /* Se distingue el clic del arrastre: girar el camión no tiene que abrir
     el panel de una rueda cada vez. */
  let desde = null;
  ren.domElement.addEventListener('pointerdown', e => desde = [e.clientX, e.clientY]);
  ren.domElement.addEventListener('pointerup', e => {
    if (!desde) return;
    const lejos = Math.hypot(e.clientX - desde[0], e.clientY - desde[1]) > 6;
    desde = null;
    if (lejos) return;
    const golpe = enRueda(e);
    elegirEsquina(golpe ? esquinaDelPunto(golpe.point, golpe.object) : null);
  });
  ren.domElement.addEventListener('pointermove', e => {
    ren.domElement.style.cursor = enRueda(e) ? 'pointer' : 'grab';
  });

  const medir = () => {
    if (!V.render) return;
    cam.aspect = caja.clientWidth / caja.clientHeight;
    cam.updateProjectionMatrix();
    ren.setSize(caja.clientWidth, caja.clientHeight);
  };
  new ResizeObserver(medir).observe(caja);

  (function dibujar(){
    if (!V.render) return;
    V.anim = requestAnimationFrame(dibujar);
    ctrl.update();
    ren.render(esc3, cam);
  })();
}

/* De qué eje y de qué lado es una rueda, mirando dónde está.

   El lado puede quedar en "ambos": hay modelos que traen las dos ruedas de
   un eje en una sola pieza, y esa pieza no es de un lado ni del otro. */
function esquinaDeLaRueda(malla){
  if (malla.userData.eje) {
    return { eje:malla.userData.eje, lado:malla.userData.lado };
  }
  const c = new THREE.Box3().setFromObject(malla);
  return { eje: ejeMasCerca((c.min.z + c.max.z) / 2),
           lado: c.max.x < 0 ? 'I' : c.min.x > 0 ? 'D' : 'ambos' };
}

/* Se pinta la rueda elegida, y nada más. Nada de marcas flotando al lado:
   la rueda es lo que se tocó y es lo que tiene que quedar marcado.

   Naranja la elegida, rojiza la esquina a la que le falta alguna cubierta,
   gris el resto. Una pieza que abarca las dos ruedas de un eje se pinta
   cuando la esquina elegida es de ese eje, del lado que sea: no se puede
   pintar media pieza. */
function pintarRuedas(){
  for (const m of V.ruedas){
    const e = esquinaDeLaRueda(m);
    const suya = V.esquina && e.eje === V.esquina.eje &&
                 (e.lado === 'ambos' || e.lado === V.esquina.lado);
    let color = 0x24282d;
    if (suya) color = 0xff7a1a;
    else if (e.lado !== 'ambos' &&
             posicionesDe(e).some(p => !p.cubierta_id)) color = 0x6d3a34;
    m.material.color.setHex(color);
    m.material.emissive.setHex(suya ? 0x3a1a04 : 0x000000);
  }
}

/* A qué eje del mapa de cubiertas corresponde uno del modelo.

   Lo normal es que sean los mismos y estén en el mismo orden. Cuando no
   —el modelo es genérico y el mapa es el de la unidad— el primero es el
   primero, el último es el último, y los del medio caen en el que llegue:
   más vale mostrar el eje de al lado que no mostrar nada. */
function ejeDelMapa(numero){
  const mapa = VISOR.mapa || [];
  const ejes = [...new Set(mapa.filter(p => !p.es_auxilio).map(p => p.eje))]
    .sort((a, b) => a - b);
  if (!ejes.length) return null;
  if (ejes.length === V.ejes.length) return ejes[numero - 1];
  if (numero === 1) return ejes[0];
  if (numero === V.ejes.length) return ejes[ejes.length - 1];
  return ejes[Math.min(numero, ejes.length) - 1];
}

function posicionesDe(esquina){
  const mapa = VISOR.mapa || [];
  const eje = ejeDelMapa(esquina.eje);
  return eje == null ? []
    : mapa.filter(p => !p.es_auxilio && p.lado === esquina.lado &&
                       p.eje === eje);
}
