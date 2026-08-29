#!/usr/bin/env python3
"""Trae las respuestas de la micro-encuesta del log de nginx a SQLite.

POR QUÉ ESTO Y NO UN SERVICIO. En tasa no hay ningún proceso escuchando: nginx
sirve estático y proxea, y el colector es un cron que SALE a buscar. Levantar un
servicio para recoger 200 respuestas sería meterle al único proyecto que
funciona una pieza más que vigilar y que se puede caer. Así que /api/encuesta no
procesa nada —anota la línea y contesta 204— y esto la ingiere después. El
endpoint no tiene forma de fallar porque no ejecuta código.

LO QUE CUESTA: el dato pasa por un archivo, así que hay que llevar la cuenta de
por dónde se iba (offset + inode) y drenar el rotado antes de saltar al nuevo.
Eso está resuelto abajo y es la única parte delicada del script.

Corre por cron cada hora, al lado de recolectar.py. Ingerir dos veces no
duplica: el offset solo avanza, y los correos llevan UNIQUE.

    ingerir_encuesta.py              # ingiere lo nuevo
    ingerir_encuesta.py --resumen    # lee el resultado
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import date
from urllib.parse import parse_qs

LOG = os.environ.get("TASA_ENCUESTA_LOG", "/var/log/tasa/encuesta.log")
DB = os.environ.get("TASA_DB", "/opt/tasa-historico/tasa.db")
ESTADO = os.environ.get("TASA_ENCUESTA_ESTADO", "/opt/tasa-historico/.encuesta_offset.json")
ESQUEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "esquema.sql")

# EL UMBRAL, ESCRITO ANTES DE MIRAR NADA. Es lo único que hace honesta la
# prueba: si las opciones 3 y 4 juntas no llegan al 10% de las respuestas, la
# puerta del negocio se cierra y no se vuelve a abrir. Se lee a las 200
# respuestas o el 19-sep-2026, lo que llegue primero. No se lee antes ni se
# ajusta el umbral después — por eso el script se niega a dar veredicto todavía
# en vez de dejarlo a la fuerza de voluntad de quien lo corre.
#
# EL DENOMINADOR SON LAS RESPUESTAS, NUNCA LAS IMPRESIONES. Va en mayúsculas
# porque desde que se cuenta la impresión hay dos denominadores posibles en esta
# misma base, y calcular el 10% sobre impresiones cerraría la puerta por error
# casi seguro. Las impresiones sirven para OTRA COSA: distinguir "no la vieron"
# de "la vieron y no les interesó". Son diagnóstico de la pieza, no medida del
# interés, y no entran en el veredicto.
#
#   VEREDICTO = (opción 3 + opción 4) / total de respuestas >= 10%
#
# Tres condiciones para que haya veredicto, y las tres solo pueden RETENERLO,
# nunca darlo por bueno de más:
#   1. 200 respuestas, o el 19-sep-2026.
#   2. Al menos 50 respuestas. Con menos, el 10% son cinco personas y eso no
#      distingue señal de ruido. A 200 son 20 y sí.
#   3. Tasa de respuesta (respuestas/impresiones) del 5% o más. Por debajo, lo
#      que falla es la pieza —no se ve bien o estorba—, no la hipótesis, y lo
#      que se revisa es la pieza.
UMBRAL = 0.10
MIN_RESPUESTAS = 200
MIN_VEREDICTO = 50
TASA_MIN = 0.05
CORTE = date(2026, 9, 19)

EVENTOS = {"v": "vista", "r": "respuesta", "x": "cerrada"}
ETIQUETAS = {
    1: "cuánto me cuesta algo",
    2: "cambiar efectivo",
    3: "cobrarle a un cliente / ponerle precio",
    4: "cuadrar cuentas / llevar mis números",
    5: "otra cosa",
}


def conectar():
    con = sqlite3.connect(DB)
    with open(ESQUEMA, encoding="utf-8") as f:
        con.executescript(f.read())
    return con


def cargar_estado():
    try:
        with open(ESTADO, encoding="utf-8") as f:
            e = json.load(f)
        return int(e.get("inode", 0)), int(e.get("offset", 0))
    except Exception:
        return 0, 0


def guardar_estado(inode, offset):
    tmp = ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"inode": inode, "offset": offset}, f)
    os.replace(tmp, ESTADO)


def completas(lineas):
    """Descarta la última línea si nginx la está escribiendo todavía.

    Sin esto, una línea leída a medias se contaría en el offset y su cola se
    perdería para siempre en la corrida siguiente. Es la misma clase de error
    que el cuerpo partido del /api/usdt de agosto: leer algo mientras alguien lo
    escribe. La línea incompleta se lee entera dentro de una hora.
    """
    if lineas and not lineas[-1].endswith("\n"):
        lineas = lineas[:-1]
    return lineas


def medir(lineas):
    return sum(len(l.encode("utf-8")) for l in lineas)


def leer_nuevo():
    """Líneas nuevas desde la última corrida, y el estado que hay que guardar.

    La rotación es el único caso con filo: cuando logrotate mueve el archivo,
    nginx escribe en uno nuevo y lo que quedó sin leer se fue al .1. Saltar
    directo al archivo nuevo perdería en silencio las respuestas de entre la
    última corrida y la rotación —hasta una hora de gente—. Por eso, al detectar
    que el inode cambió, primero se drena el .1 desde donde íbamos.
    """
    if not os.path.exists(LOG):
        return [], None

    st = os.stat(LOG)
    inode_prev, offset_prev = cargar_estado()
    lineas = []

    mismo = (st.st_ino == inode_prev) and (st.st_size >= offset_prev)
    if mismo:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            f.seek(offset_prev)
            lineas = completas(f.readlines())
        return lineas, (st.st_ino, offset_prev + medir(lineas))

    # Rotó (o lo truncaron). Drenar la cola del rotado antes de empezar el nuevo.
    rotado = LOG + ".1"
    if inode_prev and os.path.exists(rotado):
        try:
            if os.stat(rotado).st_ino == inode_prev:
                with open(rotado, encoding="utf-8", errors="replace") as f:
                    f.seek(offset_prev)
                    lineas.extend(completas(f.readlines()))
        except OSError:
            pass  # sin la cola se pierden esas líneas; el resto sigue

    with open(LOG, encoding="utf-8", errors="replace") as f:
        nuevas = completas(f.readlines())
    lineas.extend(nuevas)
    return lineas, (st.st_ino, medir(nuevas))


def entero(v, lo, hi):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def parsear(linea):
    """Una línea del log a una fila, o None si no se entiende.

    Se descarta en silencio todo lo que no encaje: el endpoint es público y
    cualquiera puede pegarle con lo que quiera. Aquí no se confía en nada.
    """
    partes = linea.rstrip("\n").split("\t", 1)
    if len(partes) != 2:
        return None
    ts, args = partes[0].strip(), partes[1].strip()
    if not ts or not args:
        return None
    try:
        q = parse_qs(args, keep_blank_values=False)
    except Exception:
        return None

    ev = (q.get("ev") or [""])[0]
    if ev in EVENTOS:
        op = entero((q.get("op") or [None])[0], 1, 5) if ev == "r" else None
        pos = entero((q.get("pos") or [None])[0], 1, 5) if op else None
        orden = (q.get("ord") or [""])[0][:5] or None
        if orden and (len(orden) != 5 or sorted(orden) != list("12345")):
            orden = None
        if ev == "r" and op is None:
            return None  # respuesta sin opción válida no es una respuesta
        return ("encuesta", (ts, EVENTOS[ev], op, pos, orden))

    if ev == "t":
        txt = (q.get("v") or [""])[0].strip()[:240]
        return ("encuesta_texto", (ts, txt)) if txt else None

    if ev == "m":
        correo = (q.get("v") or [""])[0].strip().lower()[:120]
        if "@" not in correo or "." not in correo.split("@")[-1]:
            return None
        return ("encuesta_correo", (ts, correo))

    return None


def ingerir():
    lineas, estado = leer_nuevo()
    if estado is None:
        print("sin log todavía:", LOG)
        return 0

    con = conectar()
    n = {"encuesta": 0, "encuesta_texto": 0, "encuesta_correo": 0}
    for linea in lineas:
        fila = parsear(linea)
        if not fila:
            continue
        tabla, valores = fila
        if tabla == "encuesta":
            cur = con.execute(
                "INSERT INTO encuesta (ts, evento, opcion, posicion, orden) VALUES (?,?,?,?,?)", valores
            )
        elif tabla == "encuesta_texto":
            cur = con.execute("INSERT INTO encuesta_texto (ts, texto) VALUES (?,?)", valores)
        else:
            cur = con.execute("INSERT OR IGNORE INTO encuesta_correo (ts, correo) VALUES (?,?)", valores)
        # rowcount y no +1 a secas: el correo repetido no entra (UNIQUE) y
        # contarlo daría una lista de testers más larga de lo que es.
        if cur.rowcount:
            n[tabla] += 1
    con.commit()
    con.close()
    guardar_estado(*estado)
    print(
        "ingeridas: %d eventos, %d textos, %d correos (de %d líneas)"
        % (n["encuesta"], n["encuesta_texto"], n["encuesta_correo"], len(lineas))
    )
    return sum(n.values())


def resumen():
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    q = con.execute("SELECT evento, COUNT(*) FROM encuesta GROUP BY evento").fetchall()
    tot = dict(q)
    vistas = tot.get("vista", 0)
    resp = tot.get("respuesta", 0)
    cerradas = tot.get("cerrada", 0)

    print("vistas: %d · respuestas: %d · cerradas: %d" % (vistas, resp, cerradas))
    if vistas:
        print("tasa de respuesta: %.1f%% de quien la vio" % (100.0 * resp / vistas))
    if not resp:
        print("\nTodavía no hay respuestas.")
        return

    print()
    conteo = dict(con.execute(
        "SELECT opcion, COUNT(*) FROM encuesta WHERE evento='respuesta' GROUP BY opcion"
    ).fetchall())
    for op in range(1, 6):
        c = conteo.get(op, 0)
        print("  %d. %-40s %4d  %5.1f%%" % (op, ETIQUETAS[op], c, 100.0 * c / resp))

    # Sobre RESPUESTAS. Las impresiones no entran aquí; ver la nota del umbral.
    negocio = conteo.get(3, 0) + conteo.get(4, 0)
    pct = 100.0 * negocio / resp
    print("\n  3+4 (la prueba): %d de %d respuestas = %.1f%%   [umbral: %.0f%% de las"
          % (negocio, resp, pct, UMBRAL * 100))
    print("  respuestas, NO de las impresiones]")

    # Sesgo de posición: si una posición se lleva sistemáticamente más votos, el
    # barajado no bastó y el reparto por opción hay que leerlo con eso encima.
    pos = dict(con.execute(
        "SELECT posicion, COUNT(*) FROM encuesta WHERE evento='respuesta' AND posicion IS NOT NULL GROUP BY posicion"
    ).fetchall())
    if pos:
        print("\n  por posición en pantalla: " + " ".join(
            "%dº=%d" % (p, pos.get(p, 0)) for p in range(1, 6)
        ))

    textos = con.execute("SELECT ts, texto FROM encuesta_texto ORDER BY id").fetchall()
    correos = con.execute("SELECT COUNT(*) FROM encuesta_correo").fetchone()[0]
    print("\n  correos para probar el Android: %d  (Google pide 12)" % correos)
    if textos:
        print("\n  'otra cosa' (%d):" % len(textos))
        for ts, t in textos:
            print("    · " + t)

    # El veredicto no se da antes de tiempo, y el script no lo deja dar. Leer a
    # medio camino y ajustar el umbral después es exactamente lo que convierte
    # una prueba en una excusa.
    print()
    hoy = date.today()

    # 1. No se lee antes de tiempo. Leer a medio camino y ajustar el umbral
    #    después es lo que convierte una prueba en una excusa.
    if resp < MIN_RESPUESTAS and hoy < CORTE:
        print("SIN VEREDICTO todavía: faltan %d respuestas o llegar al %s."
              % (MIN_RESPUESTAS - resp, CORTE.isoformat()))
        return

    # 2. n mínimo. Sin esto, el umbral mide ruido con cara de dato.
    if resp < MIN_VEREDICTO:
        print("SIN VEREDICTO. n = %d, y por debajo de %d el %.0f%% son %d personas:"
              % (resp, MIN_VEREDICTO, UMBRAL * 100, round(resp * UMBRAL)))
        print("eso no distingue señal de ruido. No cierra NI abre — 'no alcanzó para")
        print("saber'. Mira las vistas: si son pocas, el problema es que no la vieron.")
        return

    # 3. Si casi nadie responde, lo que falla es la pieza y no la hipótesis. Esta
    #    condición existe gracias al conteo de impresiones: sin denominador no
    #    habría forma de distinguir un mal resultado de una pieza mal puesta.
    tasa = (resp / vistas) if vistas else 0.0
    if tasa < TASA_MIN:
        print("SIN VEREDICTO SOBRE EL NEGOCIO. Responde el %.1f%% de quien la ve, por"
              % (tasa * 100))
        print("debajo del %.0f%% mínimo. Eso no dice nada de la gente: dice que la pieza"
              % (TASA_MIN * 100))
        print("no se está viendo bien o que estorba. Lo que se revisa es la pieza.")
        return

    if pct >= UMBRAL * 100:
        print("PASA. %.1f%% de las respuestas cobra o lleva números en dos monedas." % pct)
        print("Hay a quién construirle.")
    else:
        print("NO PASA. %.1f%% de las respuestas contra un umbral de %.0f%%." % (pct, UMBRAL * 100))
        print("La puerta se cierra.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--resumen", action="store_true", help="lee el resultado en vez de ingerir")
    args = ap.parse_args()
    if args.resumen:
        resumen()
    else:
        ingerir()
    return 0


if __name__ == "__main__":
    sys.exit(main())
