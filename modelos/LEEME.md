# Los modelos 3D

Un `.obj` por tipo de camión. La pantalla de Flota lo dibuja al abrir una
unidad y se puede girar, acercar y **tocar las ruedas para cambiar las
cubiertas ahí mismo**.

| Archivo | Para qué camiones | Unidades |
|---|---|---|
| `iveco-4x2.obj` | tractores de dos ejes | 10 |
| `iveco-6x2.glb` | tractores de tres ejes (6x2 y 6x4) | 8 |

**Cuidado al subirlos a GitHub:** subir el archivo anda, pero **renombrarlo
después desde la web lo destruye**. GitHub abre el archivo en el editor de
texto para renombrarlo, y un binario no se puede editar como texto: lo
guarda vacío. Hay que subirlo ya con el nombre final.

Se eligen **por la cantidad de ejes, no por la marca**: un tractor de tres
ejes se parece más a otro de tres ejes que a uno de dos de la misma marca,
y lo que importa acá es dónde están las ruedas.

## Qué necesita un modelo para servir

**`.glb`, `.gltf`, `.obj` o `.fbx`.** El mejor es el **`.glb`**: es un
solo archivo, pesa menos y se lee más rápido. El mismo camión pasó de 7,4 MB
en FBX a 930 KB en glb, con 14.916 triángulos en vez de 249.084. El FBX se acepta porque es como vienen
casi todos los modelos que se consiguen, y convertirlos sería un paso más
que se puede saltear. El archivo va como `modelos/iveco-<clave>.obj` o
`.fbx`; la app busca los dos y usa el que encuentre.

**No hace falta que venga prolijo.** La app lo acomoda sola al cargarlo, en
este orden:

1. **Le saca las luces y la cámara.** Los FBX traen adentro las que usó el
   que lo armó, y le pegan de más: el piso queda blanco y la carrocería se
   aplana. La escena pone las suyas.
2. **Lo para.** Si viene parado en Z —así exporta media herramienta— se lo
   acuesta.
3. **Lo endereza.** Los modelos vienen girados en cualquier ángulo, no solo
   en múltiplos de noventa grados: el 6x2 venía en diagonal, a cuarenta
   grados. La dirección de marcha no se puede sacar de la caja —un camión en
   diagonal tiene la caja casi cuadrada— pero sí de las ruedas: **los ejes
   están alineados con el camión, siempre**. Se toma la recta que va de la
   rueda más adelantada a la más atrasada y se la gira hasta que apunte al
   eje Z.
4. **Lo escala.** Si mide 3.744 en vez de 6,5, se lo lleva a los seis metros
   y medio de un tractor.
5. **Lo apoya.** Se lo centra y se lo sienta en el piso, venga hundido o
   flotando.

**Las ruedas se encuentran solas.** Primero por los nombres que usa el repo:

```
rueda_frente_izq   rueda_frente_der
rueda_atras_izq    rueda_atras_der
carroceria
```

Y si no, por **cualquier palabra de rueda en cualquier idioma** —`rueda`,
`wheel`, `tire`, `llanta`, `kerek`, `gumi`, `rad`, `roue`— o por la sigla
que usan los modelos de juegos: **FL, FR, ML, MR, RL, RR**. Y si tampoco,
**por dónde están**: los pedazos de abajo, redondos y de un tamaño
razonable. Se mira el nombre de la malla y el de los nodos que la
contienen, porque en un glTF las mallas se llaman todas «model».

**Los colliders no cuentan.** Son cajas invisibles para las físicas del
juego del que salió el modelo, y abarcan el camión entero: si entraran, le
falsearían el tamaño, el centro y el enderezado.

**La esquina sale de dónde se tocó, no de qué pieza.** Muchos modelos traen
las dos ruedas de un eje en una sola pieza: preguntarle a la pieza de qué
lado está no tiene respuesta, preguntarle al dedo sí. Por eso se usa el
punto exacto del clic.

La rueda elegida **se pinta de naranja**. Una pieza que abarca las dos
ruedas de un eje se pinta cuando la esquina elegida es de ese eje, del lado
que sea: no se puede pintar media pieza.

Si en algún modelo no reconoce ninguna rueda, el camión se ve igual y la
pista de abajo lo dice.

**Lo único que sí importa: el peso.** El navegador se lo baja cada vez que
se abre una unidad. El Hi-Way que está andando pesa 240 KB con 2.322
triángulos y alcanza de sobra. Apuntar a **menos de 1 MB**.

Para achicar uno pesado, en Blender: borrar interior, motor y chasis por
dentro; **Decimate con ratio 0.05** en la carrocería —las ruedas no, que se
tocan y quedarían con los bordes rotos—; exportar sin materiales.

No hacen falta texturas ni `.mtl`: la app le pone su propio material,
carrocería blanca y gomas negras, que es como se ven los camiones de la
empresa.

## Cómo se elige cuál va

Por la cantidad de ejes, buscándola en este orden:

1. **Cuántas gomas lleva el mapa**, si la unidad lo tiene asignado. Es el
   dato duro y es el que usa el gomero: **6 gomas es un 4x2, 10 es un
   6x2**. El auxilio no cuenta. Le gana a todo lo demás — un `600S44` con
   seis gomas es un 4x2, diga lo que diga el código.
2. **Lo que diga el modelo**, cuando lo dice: `6X2`, `6X4`, `4X2`.
3. **El código de Iveco.** El número de tres cifras antes de la S es el peso
   bruto combinado en toneladas por diez: `490S44` son 49 toneladas y
   `600S44` son 60. Sesenta toneladas no las lleva un chasis de dos ejes,
   así que de 56 para arriba son tres ejes.
4. Si no se puede saber, se dibuja el de dos ejes, que es el más común en
   la flota.

La ficha **dice de dónde salió** —"por el mapa de cubiertas", "por el
código de Iveco"— al lado del nombre del camión, para poder desconfiar de
las deducidas del nombre sin tener que abrir el código. Cuando no acierta,
se fuerza desde el campo **Modelo 3D** de la ficha y la deducción no se
mete más con esa unidad.

Los 50 vehículos que no son tractores —las Daily de reparto, las
camionetas, los Mercedes chicos— no llevan modelo, y la ficha lo dice.

## Lo que hay que saber de este modelo

Los modelos dibujan las ruedas de a una por lado, pero los ejes traseros
son duales: donde el dibujo muestra una rueda, el camión lleva dos. Por eso
tocar una rueda trasera no selecciona *una* posición sino **todas las de
atrás de ese lado**, y la lista de abajo dice cuáles son. El mapa de gomería sigue siendo el que
manda; esto sirve para encontrar la posición mirando el camión en vez de
leyendo códigos.

El archivo salió de un modelo de simulador: los nombres de material del
original apuntaban a texturas de ese juego. Se quitaron al importarlo, pero
la geometría es de ahí. Para uso interno no molesta; si algún día esto sale
de la empresa, conviene reemplazarlo por uno propio o con licencia.

## Cómo agregar otro

1. Exportarlo a `.obj` o `.fbx`, con las ruedas como objetos separados.
2. Guardarlo como `modelos/iveco-<clave>.obj` o `.fbx`. Se puede subir
   directo desde GitHub: **Add file → Upload files**, dentro de `modelos/`.
3. Agregar la clave a `MODELOS_3D` en `gomeria/unidades.py`.
4. Sumar la opción al `<select>` de **Modelo 3D** en `unidades.html`.
