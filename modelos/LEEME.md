# Los modelos 3D

Un `.obj` por tipo de camión. La pantalla de Flota lo dibuja al abrir una
unidad y se puede girar, acercar y **tocar las ruedas para cambiar las
cubiertas ahí mismo**.

| Archivo | Camión | Unidades que le tocan |
|---|---|---|
| `iveco-hiway.obj` | Iveco Stralis Hi-Way / Hi-Road | 11 |
| `iveco-sway.obj` | Iveco S-Way | 4 — **falta el archivo** |

## Qué necesita un modelo para servir

Dos cosas, y ninguna es difícil:

1. **Las ruedas tienen que ser objetos separados**, con estos nombres
   exactos:

   ```
   rueda_frente_izq   rueda_frente_der
   rueda_atras_izq    rueda_atras_der
   carroceria
   ```

   Sin eso el camión se ve pero no se puede tocar nada.

2. **En metros y con el piso en Y = 0.** La cámara se acomoda sola al
   tamaño, así que no importa si el camión es más largo o más corto, pero
   si viene en centímetros aparece gigante y si viene con el piso en otro
   lado queda hundido o flotando.

No hacen falta texturas ni `.mtl`: la app le pone su propio material,
carrocería blanca y gomas negras, que es como se ven los camiones de la
empresa. Un `.mtl` en el mismo directorio se ignora.

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

1. Exportarlo a `.obj` desde Blender con las ruedas separadas y renombradas.
2. Guardarlo como `modelos/iveco-<clave>.obj`.
3. Agregar la clave a `MODELOS_3D` en `gomeria/unidades.py`, con las
   palabras que lo identifican en el texto del modelo.
4. Sumar la opción al `<select>` de **Modelo 3D** en `unidades.html`.
