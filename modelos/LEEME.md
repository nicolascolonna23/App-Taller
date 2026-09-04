# Los modelos 3D

Un `.obj` por tipo de camión. La pantalla de Flota lo dibuja al abrir una
unidad y se puede girar, acercar y **tocar las ruedas para cambiar las
cubiertas ahí mismo**.

| Archivo | Camión | Unidades que le tocan |
|---|---|---|
| `iveco-hiway.obj` | Iveco Stralis Hi-Way / Hi-Road | 11 |
| `iveco-sway.obj` o `.fbx` | Iveco S-Way | 4 — **falta el archivo** |

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

La app lo deduce del modelo cargado en el maestro: un *S-WAY* dibuja el
S-Way; un *STRALIS*, *HI ROAD*, *AS490* o *600S44* dibuja el Hi-Way. Cuando
no acierta, se fuerza desde el campo **Modelo 3D** de la ficha.

De los 53 vehículos, 15 tienen modelo. Los otros 38 —Mercedes, Ford,
Scania, las Daily de reparto— no tienen uno todavía y la ficha lo dice.

## Lo que hay que saber de este modelo

`iveco-hiway.obj` es un **tractor de dos ejes**. Los 6x2 de la flota tienen
tres, y el dibujo no muestra el tercero. Por eso tocar una rueda trasera no
selecciona *una* posición sino **todas las de atrás de ese lado**, y la
lista de abajo dice cuáles son. El mapa de gomería sigue siendo el que
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
3. Agregar la clave a `MODELOS_3D` en `gomeria/unidades.py`, con las
   palabras que lo identifican en el texto del modelo.
4. Sumar la opción al `<select>` de **Modelo 3D** en `unidades.html`.
