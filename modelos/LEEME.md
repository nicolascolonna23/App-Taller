# Los modelos 3D

Un `.obj` por tipo de camión. La pantalla de Flota lo dibuja al abrir una
unidad y se puede girar, acercar y **tocar las ruedas para cambiar las
cubiertas ahí mismo**.

| Archivo | Para qué camiones | Unidades |
|---|---|---|
| `iveco-4x2.obj` | tractores de dos ejes | 10 |
| `iveco-6x2.fbx` | tractores de tres ejes (6x2 y 6x4) | 8 |

Se eligen **por la cantidad de ejes, no por la marca**: un tractor de tres
ejes se parece más a otro de tres ejes que a uno de dos de la misma marca,
y lo que importa acá es dónde están las ruedas.

## Qué necesita un modelo para servir

**`.obj` o `.fbx`, los dos sirven.** El FBX se acepta porque es como vienen
casi todos los modelos que se consiguen, y convertirlos sería un paso más
que se puede saltear. El archivo va como `modelos/iveco-<clave>.obj` o
`.fbx`; la app busca los dos y usa el que encuentre.

**No hace falta que venga prolijo.** La app lo acomoda sola al cargarlo:

- **Lo para.** Si el modelo viene parado en Z —así exporta media
  herramienta— se lo acuesta. Se detecta porque en un camión el lado más
  largo tiene que ser el largo, no el alto.
- **Lo escala.** Si viene en centímetros o en pulgadas, se lo lleva a los
  6,5 metros de un tractor.
- **Lo apoya.** Se lo centra y se lo sienta en el piso, aunque venga
  hundido o flotando.

**Las ruedas se encuentran solas.** Primero por nombre, si el modelo trae
estos:

```
rueda_frente_izq   rueda_frente_der
rueda_atras_izq    rueda_atras_der
carroceria
```

Y si no —que es lo normal, cada modelo las llama distinto o las deja como
`Object_012`— se buscan **por dónde están**: son los pedazos de abajo,
corridos hacia los costados, redondos y de un tamaño razonable. Después se
las reparte en las cuatro esquinas por su posición.

Si en algún modelo no las reconoce, el camión se ve igual y la pista de
abajo lo dice; ahí conviene renombrar los objetos a mano, que es el camino
exacto.

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
