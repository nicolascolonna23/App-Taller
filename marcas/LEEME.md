# Los logos de las marcas de cubierta

Un `.png` por marca, con **fondo transparente** y el nombre en minúsculas,
sin espacios ni signos:

| Marca, como está cargada en la base | Archivo |
|---|---|
| MICHELIN | `michelin.png` |
| BRIDGESTONE | `bridgestone.png` |
| FATE | `fate.png` |
| APLUS | `aplus.png` |
| BF GOODRICH | `bfgoodrich.png` |
| PIRELLI | `pirelli.png` |
| FIRESTONE | `firestone.png` |

La regla es la misma siempre: se toma la marca como figura en la cubierta,
se pasa a minúsculas y se le sacan espacios, puntos y guiones. *BF
Goodrich* y *BFGoodrich* dan las dos `bfgoodrich.png`.

Si una marca no tiene logo, se muestra el nombre en texto y listo. No hay
que cargar nada para que la app ande.

## Cómo subirlos

En GitHub: **Add file → Upload files**, entrar a la carpeta `marcas/` y
arrastrarlos. Conviene renombrarlos **antes** de subirlos, en la
computadora: renombrar un binario desde la web de GitHub lo destruye,
porque lo abre en el editor de texto.

## Qué tamaño

Chicos: se muestran a 16 píxeles de alto. Con **64 píxeles de alto** alcanza
de sobra y pesan nada. Un logo de 2 MB no se ve mejor, solo tarda más.

Con fondo transparente, no blanco: van sobre el fondo oscuro de la app y un
rectángulo blanco alrededor se nota.
