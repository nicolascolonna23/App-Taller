#!/usr/bin/env python3
"""
Deja lista la conexión a Supabase.

    python3 gomeria/configurar.py

Pide la cadena de conexión, revisa que sea la correcta, prueba que entre y
la guarda en gomeria/conexion.txt. No hay que crear ningún archivo a mano.
"""
import getpass, os, re, sys
from urllib.parse import quote, urlsplit, urlunsplit

AQUI = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.join(AQUI, "conexion.txt")

TABLAS = ["configuraciones", "configuracion_posiciones", "unidades", "cubiertas",
          "montajes", "partes", "movimientos", "mediciones"]


PLACEHOLDERS = ("[YOUR-PASSWORD]", "[TU-PASSWORD]", "[YOUR_PASSWORD]", "[PASSWORD]")


def sin_placeholder(url):
    """Saca el [YOUR-PASSWORD] antes de parsear.

    Los corchetes hacen que Python lea el netloc como una dirección IPv6 y
    falle, justo en el caso más común: pegar la cadena tal cual la da Supabase.
    """
    for ph in PLACEHOLDERS:
        url = url.replace(ph, "x")
    return url


def revisar(url):
    """Devuelve un texto con el problema, o None si la cadena está bien."""
    if not url:
        return "No pegaste nada."
    if url.startswith(("'", '"')) or url.endswith(("'", '"')):
        return "Sacale las comillas del principio y del final."
    try:
        urlsplit(sin_placeholder(url))
    except ValueError:
        return ("Esa cadena está mal formada. Copiala de nuevo entera desde "
                "Supabase, sin editarla.")
    if not url.startswith("postgresql://") and not url.startswith("postgres://"):
        return ("Eso no parece una cadena de conexión. Tiene que empezar con "
                "postgresql:// — fijate que copiaste la de 'Connection String', "
                "no la URL del proyecto ni una clave de API.")
    if ":6543" in url:
        return ("Esa es la del Transaction pooler (puerto 6543) y no sirve para esto. "
                "Volvé a Connect y elegí Session pooler, que usa el puerto 5432.")
    if "YOUR-PROJECT" in url or "example.com" in url:
        return "Esa cadena es el ejemplo de la documentación, no la de tu proyecto."
    # Con el Session pooler el usuario lleva el identificador del proyecto pegado
    # (postgres.abcdefgh). Si es "postgres" pelado, copiaron la conexión directa.
    partes = urlsplit(sin_placeholder(url))
    if (partes.username or "") == "postgres" and "pooler" not in (partes.hostname or ""):
        return ("Esa es la cadena de 'Direct connection'. Necesito la de "
                "'Session pooler': en Supabase, botón verde Connect → Connection "
                "String → Session pooler. Se reconoce porque el usuario es "
                "postgres.ALGO y el servidor dice pooler.supabase.com.")
    return None


def poner_password(url, password):
    """Mete la contraseña en la cadena, escapando los símbolos.

    Una contraseña con @ o / rompe la cadena si va tal cual: el @ separa el
    usuario del servidor. Por eso se pide aparte y se codifica acá.
    """
    p = urlsplit(sin_placeholder(url))
    usuario = quote(p.username or "postgres", safe="")
    clave = quote(password, safe="")
    puerto = f":{p.port}" if p.port else ""
    neto = f"{usuario}:{clave}@{p.hostname}{puerto}"
    return urlunsplit((p.scheme, neto, p.path, p.query, p.fragment))


def probar(url):
    """Conecta y cuenta qué hay. Devuelve (ok, mensaje)."""
    try:
        import psycopg
    except ImportError:
        return False, ("Falta una librería. Corré primero:\n"
                       "    pip3 install -r gomeria/requisitos.txt")
    try:
        with psycopg.connect(url, connect_timeout=20) as cx:
            faltan = [t for t in TABLAS
                      if not cx.execute("select to_regclass(%s)", (f"public.{t}",)).fetchone()[0]]
            if faltan:
                return False, ("Entré a la base, pero le faltan tablas: "
                               + ", ".join(faltan) +
                               "\n  Corré 01_esquema.sql y 02_vistas.sql en el SQL Editor "
                               "de Supabase y volvé a probar.")
            # Las tablas tienen RLS prendido. El dueño de la tabla lo saltea, pero
            # cualquier otro rol vería la base vacía y sin ningún error: es el
            # tipo de problema que cuesta horas encontrar. Mejor avisar acá.
            d = cx.execute("""
                select pg_get_userbyid(c.relowner) as dueno, current_user as yo,
                       coalesce((select rolbypassrls from pg_roles
                                 where rolname = current_user), false) as saltea
                from pg_class c
                join pg_namespace n on n.oid = c.relnamespace
                where c.relname = 'unidades' and n.nspname = 'public'""").fetchone()
            if d and d[0] != d[1] and not d[2]:
                return False, (
                    f"Conecté como '{d[1]}', pero las tablas son de '{d[0]}'.\n"
                    "  Con ese usuario no vas a ver ninguna fila, por la seguridad a\n"
                    "  nivel de fila que tienen las tablas. Usá la cadena de conexión\n"
                    "  que da Supabase, que entra como dueño.")

            unidades = cx.execute("select count(*) from unidades").fetchone()[0]
            cubiertas = cx.execute("select count(*) from cubiertas").fetchone()[0]
            return True, f"Las 8 tablas están. Hay {unidades} unidades y {cubiertas} cubiertas cargadas."
    except Exception as e:
        detalle = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
        pista = ""
        if "password authentication failed" in detalle.lower():
            pista = ("\n  La contraseña no es la correcta. Podés resetearla en Supabase: "
                     "Settings → Database → Reset database password.")
        elif "could not translate host name" in detalle.lower() or "name or service" in detalle.lower():
            pista = "\n  No se pudo resolver la dirección. Revisá que copiaste la línea entera."
        elif "timeout" in detalle.lower():
            pista = ("\n  No hubo respuesta. Si el proyecto estuvo una semana sin uso, "
                     "Supabase lo pausa: entrá al panel y despausalo.")
        return False, f"No pude conectarme: {detalle}{pista}"


def main():
    print("Conexión a Supabase")
    print("-" * 60)
    print("En Supabase, botón verde Connect (arriba) → Connection String →")
    print("Session pooler. Copiá esa línea y reemplazá [YOUR-PASSWORD] por tu")
    print("contraseña.")
    print()

    if os.path.exists(DESTINO):
        actual = open(DESTINO, encoding="utf-8").read().strip()
        if actual:
            print(f"Ya hay una conexión guardada: ...{actual[-38:]}")
            if input("¿La reemplazo? [s/N] ").strip().lower() not in ("s", "si", "sí"):
                ok, msg = probar(actual)
                print("\n" + ("OK. " if ok else "") + msg)
                return 0 if ok else 1
            print()

    try:
        url = input("1) Pegá la cadena acá y apretá Enter.\n"
                    "   Podés dejar el [YOUR-PASSWORD] como está, la contraseña te la\n"
                    "   pido aparte en el paso siguiente.\n> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado.")
        return 1

    problema = revisar(url)
    if problema:
        print(f"\n{problema}")
        return 1

    try:
        password = getpass.getpass("\n2) Contraseña de la base (no se ve al tipear): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado.")
        return 1
    if not password:
        print("\nSin contraseña no puedo conectarme.")
        return 1

    url = poner_password(url, password)

    print("\nProbando la conexión…")
    ok, msg = probar(url)
    if not ok:
        print(msg)
        print("\nNo guardé nada. Corregí eso y volvé a correr este programa.")
        return 1

    with open(DESTINO, "w", encoding="utf-8") as f:
        f.write(url + "\n")
    os.chmod(DESTINO, 0o600)   # solo tu usuario puede leerlo: tiene la contraseña

    print(msg)
    print(f"\nGuardado en {DESTINO}")
    print("Ese archivo no se sube al repositorio: tiene la contraseña adentro.")
    print("\nSigue: python3 gomeria/cargar_unidades.py gomeria/unidades.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
