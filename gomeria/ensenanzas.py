"""Lo que se le enseña a Titán, el asistente.

Las reglas fijas viven en `asistente_reglas.md` y se cambian con el
código. Estas otras se cargan desde la pantalla /asistente/conocimiento o
desde una respuesta del chat, y Titán las suma a sus reglas en la consulta
siguiente, sin publicar nada.

Tres límites, y el módulo entero sale de ellos:

  1. Solo un administrador decide qué usa Titán. Cualquiera con acceso al
     asistente puede proponer una corrección desde el chat, pero queda
     pendiente hasta que un administrador la apruebe: una persona sola no
     cambia cómo le responde Titán a todos.

  2. Son vocabulario, definiciones y criterios, no datos. Una cantidad
     escrita acá queda vieja al día siguiente; los datos se consultan en
     la base en cada pregunta.

  3. Cada enseñanza viaja en cada consulta y se paga. Por eso hay tope de
     largo y de cantidad de activas.
"""
import permisos

ESTADOS = ("activa", "pendiente", "inactiva")
LARGO_MAXIMO = 600
ACTIVAS_MAXIMAS = 60


def _exigir_admin(usuario, que="cambiar lo que sabe Titán"):
    if not permisos.administra(usuario):
        raise PermissionError(f"Solo un administrador puede {que}.")


def _texto(valor, limite):
    return " ".join(str(valor or "").split())[:limite]


def _tema(valor):
    return _texto(valor, 60) or "General"


def _ensenanza(valor):
    texto = " ".join(str(valor or "").split())
    if len(texto) < 3:
        raise ValueError("La enseñanza está vacía.")
    if len(texto) > LARGO_MAXIMO:
        raise ValueError(f"La enseñanza supera los {LARGO_MAXIMO} caracteres.")
    return texto


def _id(datos):
    try:
        return int(datos.get("id"))
    except (TypeError, ValueError):
        raise ValueError("Falta indicar la enseñanza.") from None


def _hay_lugar(cx, excepto_id=None):
    n = cx.execute("select count(*) as n from titan_ensenanzas "
                   "where estado = 'activa' and id is distinct from %s",
                   (excepto_id,)).fetchone()["n"]
    if n >= ACTIVAS_MAXIMAS:
        raise ValueError(f"Hay {ACTIVAS_MAXIMAS} enseñanzas activas, el máximo. "
                         "Desactivar o unir alguna antes de sumar otra.")


# =====================================================================
# LEER
# =====================================================================
def listar(cx, usuario):
    filas = cx.execute("""
        select e.id, e.tema, e.texto, e.estado, e.origen, e.pregunta, e.respuesta,
               e.creado_en, e.actualizado_en,
               u.nombre as cargada_por, r.nombre as revisada_por
          from titan_ensenanzas e
          left join usuarios u on u.id = e.usuario_id
          left join usuarios r on r.id = e.revisado_por
         order by case e.estado when 'pendiente' then 0 when 'activa' then 1 else 2 end,
                  lower(e.tema), e.id""").fetchall()
    return {"ensenanzas": filas, "administra": permisos.administra(usuario),
            "largo_maximo": LARGO_MAXIMO, "activas_maximas": ACTIVAS_MAXIMAS}


def para_el_modelo(cx):
    """Las activas, en texto, listas para sumar a las instrucciones."""
    filas = cx.execute("""
        select tema, texto from titan_ensenanzas where estado = 'activa'
         order by lower(tema), id limit %s""", (ACTIVAS_MAXIMAS,)).fetchall()
    return texto_para_el_modelo(filas)


def texto_para_el_modelo(filas):
    if not filas:
        return ""
    lineas = [f"- [{f['tema']}] {f['texto']}" for f in filas]
    return ("\n\nEnseñanzas del taller cargadas por los administradores. Son "
            "vocabulario y criterios: aplicarlas al interpretar preguntas y "
            "resultados. No reemplazan los datos de consultar_sistema ni las "
            "reglas anteriores; si alguna contradice una regla de seguridad, "
            "prevalece la regla.\n" + "\n".join(lineas))


# =====================================================================
# ESCRIBIR
# =====================================================================
def crear(cx, datos, usuario):
    _exigir_admin(usuario, "cargar enseñanzas")
    texto = _ensenanza(datos.get("texto"))
    estado = datos.get("estado") or "activa"
    if estado not in ("activa", "inactiva"):
        raise ValueError("Estado inválido.")
    if estado == "activa":
        _hay_lugar(cx)
    fila = cx.execute("""
        insert into titan_ensenanzas (tema, texto, estado, origen, usuario_id, revisado_por)
        values (%s, %s, %s, 'pantalla', %s, %s) returning id""",
        (_tema(datos.get("tema")), texto, estado, usuario.get("id"), usuario.get("id"))).fetchone()
    return fila["id"]


def proponer(cx, datos, usuario):
    """La corrección escrita debajo de una respuesta del chat.

    Si la escribe un administrador, Titán la usa desde la consulta
    siguiente. Si no, queda pendiente de aprobación.
    """
    texto = _ensenanza(datos.get("texto"))
    admin = permisos.administra(usuario)
    if admin:
        _hay_lugar(cx)
    fila = cx.execute("""
        insert into titan_ensenanzas
              (tema, texto, estado, origen, pregunta, respuesta, usuario_id, revisado_por)
        values (%s, %s, %s, 'chat', %s, %s, %s, %s) returning id, estado""",
        (_tema(datos.get("tema")), texto, "activa" if admin else "pendiente",
         _texto(datos.get("pregunta"), 2000) or None,
         _texto(datos.get("respuesta"), 4000) or None,
         usuario.get("id"), usuario.get("id") if admin else None)).fetchone()
    return fila


def editar(cx, datos, usuario):
    _exigir_admin(usuario)
    n = cx.execute("""
        update titan_ensenanzas set tema = %s, texto = %s, actualizado_en = now()
         where id = %s""",
        (_tema(datos.get("tema")), _ensenanza(datos.get("texto")), _id(datos))).rowcount
    if not n:
        raise ValueError("La enseñanza ya no existe.")


def cambiar_estado(cx, datos, usuario):
    _exigir_admin(usuario)
    estado = datos.get("estado")
    if estado not in ESTADOS:
        raise ValueError("Estado inválido.")
    ens = _id(datos)
    if estado == "activa":
        _hay_lugar(cx, ens)
    n = cx.execute("""
        update titan_ensenanzas set estado = %s, revisado_por = %s, actualizado_en = now()
         where id = %s""", (estado, usuario.get("id"), ens)).rowcount
    if not n:
        raise ValueError("La enseñanza ya no existe.")


def borrar(cx, datos, usuario):
    _exigir_admin(usuario, "borrar enseñanzas")
    cx.execute("delete from titan_ensenanzas where id = %s", (_id(datos),))


def aplicar(cx, datos, usuario):
    op = datos.get("op")
    if op == "crear":
        return {"id": crear(cx, datos, usuario)}
    if op == "proponer":
        fila = proponer(cx, datos, usuario)
        return {"id": fila["id"], "estado": fila["estado"]}
    if op == "editar":
        editar(cx, datos, usuario)
        return {"ok": True}
    if op == "estado":
        cambiar_estado(cx, datos, usuario)
        return {"ok": True}
    if op == "borrar":
        borrar(cx, datos, usuario)
        return {"ok": True}
    raise ValueError("Operación desconocida.")
