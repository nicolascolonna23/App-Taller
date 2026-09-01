#!/usr/bin/env python3
"""
Administrar quién puede entrar al sistema.

    python3 gomeria/usuarios.py listar
    python3 gomeria/usuarios.py agregar ramon "Ramón Gómez"
    python3 gomeria/usuarios.py agregar nico "Nicolás Colonna" --rol admin
    python3 gomeria/usuarios.py clave ramon
    python3 gomeria/usuarios.py baja ramon
    python3 gomeria/usuarios.py alta ramon

La contraseña se pide en el momento, no se pasa por parámetro: así no queda
escrita en el historial de la terminal.
"""
import argparse, os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import auth, base

ROLES = {
    "operario":  "carga partes de gomería",
    "encargado": "además confirma y corrige",
    "admin":     "además administra usuarios",
}


def pedir_clave(usuario):
    print(f"\nContraseña para '{usuario}'. Se ve mientras la escribís.")
    clave = input("  >>> ").strip()
    if not clave:
        raise SystemExit("Sin contraseña no puedo crear el usuario.")
    problema = auth.revisar_clave(clave)
    if problema:
        raise SystemExit(problema)
    repetida = input("  Escribila de nuevo: ").strip()
    if clave != repetida:
        raise SystemExit("Las dos veces no coinciden. Probá otra vez.")
    return clave


def listar(cx):
    filas = cx.execute("""
        select u.*, (select count(*) from sesiones s where s.usuario_id = u.id
                     and s.expira > now()) as sesiones
        from usuarios u order by u.activo desc, u.usuario""").fetchall()
    if not filas:
        print("Todavía no hay usuarios. Creá el primero:")
        print('  python3 gomeria/usuarios.py agregar TUUSUARIO "Tu Nombre" --rol admin')
        return
    print(f"{'usuario':<14}{'nombre':<26}{'rol':<12}{'estado':<9}{'entró':<12}sesiones")
    print("-" * 78)
    for f in filas:
        entro = f["ultimo_ingreso"].strftime("%d/%m/%Y") if f["ultimo_ingreso"] else "nunca"
        print(f"{f['usuario']:<14}{f['nombre'][:24]:<26}{f['rol']:<12}"
              f"{'activo' if f['activo'] else 'de baja':<9}{entro:<12}{f['sesiones']}")


def main():
    ap = argparse.ArgumentParser(description="Usuarios del sistema")
    sub = ap.add_subparsers(dest="que", required=True)
    sub.add_parser("listar", help="Ver todos los usuarios")
    a = sub.add_parser("agregar", help="Crear un usuario")
    a.add_argument("usuario"); a.add_argument("nombre")
    a.add_argument("--rol", choices=list(ROLES), default="operario")
    c = sub.add_parser("clave", help="Cambiarle la contraseña a alguien")
    c.add_argument("usuario")
    b = sub.add_parser("baja", help="Impedirle entrar, sin borrarlo")
    b.add_argument("usuario")
    al = sub.add_parser("alta", help="Volver a habilitarlo")
    al.add_argument("usuario")
    args = ap.parse_args()

    with base.conectar() as cx:
        if args.que == "listar":
            listar(cx)
            return

        usuario = args.usuario.strip().lower()
        existe = cx.execute("select * from usuarios where usuario = %s", (usuario,)).fetchone()

        if args.que == "agregar":
            if existe:
                raise SystemExit(f"El usuario '{usuario}' ya existe. Para cambiarle la "
                                 f"contraseña: usuarios.py clave {usuario}")
            clave = pedir_clave(usuario)
            auth.crear_usuario(cx, usuario, args.nombre, clave, args.rol)
            cx.commit()
            print(f"\nListo. '{usuario}' ({args.nombre}) puede entrar como {args.rol}:")
            print(f"  {ROLES[args.rol]}")

        elif args.que == "clave":
            if not existe:
                raise SystemExit(f"No existe el usuario '{usuario}'.")
            clave = pedir_clave(usuario)
            auth.cambiar_clave(cx, existe["id"], clave)
            cx.commit()
            print(f"\nContraseña cambiada. Las sesiones abiertas de '{usuario}' se cerraron.")

        elif args.que in ("baja", "alta"):
            if not existe:
                raise SystemExit(f"No existe el usuario '{usuario}'.")
            activo = args.que == "alta"
            cx.execute("update usuarios set activo = %s where id = %s", (activo, existe["id"]))
            if not activo:
                cx.execute("delete from sesiones where usuario_id = %s", (existe["id"],))
            cx.commit()
            print(f"'{usuario}' quedó {'habilitado' if activo else 'de baja'}.")


if __name__ == "__main__":
    main()
