#!/usr/bin/env python3
"""Reconstruye la serie del BCV hacia atrás desde los xls del SMC.

El BCV publica el "tipo de cambio de referencia" en archivos trimestrales con
UNA HOJA POR DÍA HÁBIL: fecha-valor, y compra/venta de USD, EUR y otras ocho
monedas. La columna de VENTA es exactamente el número que muestra la app —
verificado contra el home del BCV (USD 748,78640000 / EUR 861,18672650 el
2026-08-02) y contra el "promedio" de dolarapi.

Por eso el histórico del BCV no se "empieza a guardar": se importa.

Dos trampas, las dos encontradas a golpes y por eso está escrito así:

1. La reconversión monetaria del 1-oct-2021 (1.000.000 Bs → 1 Bs). Q1-2021 trae
   el dólar a 2.070.854 y Q4-2021 a 4,17. Mezclarlos convierte la serie en
   basura, así que se descarta todo lo anterior a la reconversión por FECHA (no
   por archivo: un archivo de Q4 puede traer hojas de septiembre).

2. Los nombres de archivo del BCV mienten. `2_1_2c23_smc.xls` debería ser
   jul-sep 2023 y en realidad trae dos hojas de octubre; los 60 días de ese
   trimestre viven en `2_1_2c23_smc_60.xls`, que solo aparece en la página 2 del
   listado. Adivinar el patrón dejaba un hueco de 91 días sin avisar. Por eso
   esto RASPA EL LISTADO y además prueba el patrón: la unión de los dos.

Necesita xlrd (`pip install xlrd`). Contabo no lo tiene: esto corre en la torre
una sola vez y la base viaja por scp.
"""

import argparse
import os
import re
import sqlite3
import ssl
import sys
import tempfile
import urllib.request
from datetime import date, datetime, timezone

BASE = "https://www.bcv.org.ve"
LISTADO = BASE + "/estadisticas/tipo-cambio-de-referencia-smc"
ARCHIVOS = BASE + "/sites/default/files/EstadisticasGeneral/"
TRIMESTRES = "abcd"

# Día de la reconversión monetaria. Todo lo anterior está en el bolívar viejo.
RECONVERSION = date(2021, 10, 1)

# El BCV tiene la cadena de certificados incompleta; el propio nginx del sitio
# lo consume igual. Son archivos públicos de solo lectura.
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def traer(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "tasa-historico/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as res:
        return res.read()


def nombres_del_listado(paginas=6):
    """Los .xls que el BCV realmente enlaza, recorriendo la paginación."""
    nombres = set()
    for p in range(paginas):
        url = LISTADO if p == 0 else f"{LISTADO}?page={p}"
        try:
            html = traer(url, timeout=30).decode("utf-8", "replace")
        except Exception as e:
            print(f"aviso: no se pudo leer {url} ({e})", file=sys.stderr)
            continue
        hallados = set(re.findall(r"([\w.]+_smc[\w.]*\.xls)", html))
        if not hallados:
            break
        nombres |= hallados
    return nombres


def nombres_por_patron(desde_anio, hasta):
    """Los trimestres viejos que el listado ya no enlaza pero el server sirve."""
    nombres = set()
    for anio in range(desde_anio, hasta.year + 1):
        for i, letra in enumerate(TRIMESTRES, start=1):
            if anio == hasta.year and i > (hasta.month - 1) // 3 + 1:
                break
            nombres.add(f"2_1_2{letra}{anio % 100:02d}_smc.xls")
    return nombres


def leer_hoja(hoja):
    """Devuelve (fecha_valor, {'USD': (compra, venta), ...}) o None."""
    fecha = None
    tasas = {}
    for r in range(hoja.nrows):
        for c in range(hoja.ncols):
            v = hoja.cell_value(r, c)
            if not isinstance(v, str):
                continue
            if fecha is None:
                m = re.search(r"Fecha Valor:\s*(\d{2})/(\d{2})/(\d{4})", v)
                if m:
                    fecha = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
            if v.strip() in ("USD", "EUR"):
                # En la fila va la cotización contra el dólar y luego Bs./M.E.
                # Los dos últimos números son compra y venta en bolívares.
                nums = [
                    hoja.cell_value(r, cc)
                    for cc in range(hoja.ncols)
                    if isinstance(hoja.cell_value(r, cc), float)
                ]
                if len(nums) >= 2:
                    tasas[v.strip()] = (nums[-2], nums[-1])
    if not fecha or "USD" not in tasas:
        return None
    return fecha, tasas


def huecos(con):
    """Saltos de más de 4 días en la serie — 4 cubre un puente largo de feriados."""
    fechas = [
        date.fromisoformat(r[0]) for r in con.execute("SELECT fecha_valor FROM bcv ORDER BY 1")
    ]
    return [(a, b, (b - a).days) for a, b in zip(fechas, fechas[1:]) if (b - a).days > 4]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("TASA_DB", "tasa.db"))
    ap.add_argument("--desde-anio", type=int, default=RECONVERSION.year)
    args = ap.parse_args()

    try:
        import xlrd
    except ImportError:
        sys.exit("falta xlrd — instalar con: pip install xlrd")

    con = sqlite3.connect(args.db)
    esquema = os.path.join(os.path.dirname(os.path.abspath(__file__)), "esquema.sql")
    with open(esquema) as f:
        con.executescript(f.read())

    hoy = datetime.now(timezone.utc).date()
    nombres = nombres_del_listado() | nombres_por_patron(args.desde_anio, hoy)
    print(f"{len(nombres)} archivos candidatos (listado + patrón)\n")

    ahora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    tmp = tempfile.mkdtemp(prefix="bcv-smc-")
    total, viejos, problemas = 0, 0, []

    for nombre in sorted(nombres):
        ruta = os.path.join(tmp, nombre)
        try:
            datos = traer(ARCHIVOS + nombre)
            with open(ruta, "wb") as f:
                f.write(datos)
            libro = xlrd.open_workbook(ruta)
        except Exception as e:
            problemas.append(f"{nombre}: {type(e).__name__} {e}")
            continue

        filas = 0
        for hoja in libro.sheet_names():
            leida = leer_hoja(libro.sheet_by_name(hoja))
            if not leida:
                continue
            fecha, tasas = leida
            if date.fromisoformat(fecha) < RECONVERSION:
                viejos += 1
                continue
            usd_c, usd_v = tasas["USD"]
            eur_c, eur_v = tasas.get("EUR", (None, None))
            # REPLACE: el xls del SMC es la autoridad y pisa lo que haya anotado
            # el colector desde el home (que no trae las columnas de compra).
            con.execute(
                "INSERT OR REPLACE INTO bcv"
                " (fecha_valor, usd_venta, usd_compra, eur_venta, eur_compra, fuente, capturado_en)"
                " VALUES (?, ?, ?, ?, ?, 'smc-xls', ?)",
                (fecha, usd_v, usd_c, eur_v, eur_c, ahora),
            )
            filas += 1
        con.commit()
        total += filas
        print(f"  {nombre:28s} {filas:3d} días")

    lo, hi, n = con.execute("SELECT min(fecha_valor), max(fecha_valor), count(*) FROM bcv").fetchone()
    print(f"\n{total} hojas cargadas ({viejos} descartadas por ser bolívar pre-reconversión)")
    print(f"base: {n} días, {lo} → {hi}")

    # Los huecos se cantan siempre. Una serie con agujeros callados es peor que
    # no tenerla: el gráfico dibuja una recta donde no hubo dato.
    faltantes = huecos(con)
    if faltantes:
        print(f"\nhuecos de más de 4 días ({len(faltantes)}):")
        for a, b, d in faltantes:
            print(f"  {a} → {b}  ({d} días)")
    con.close()

    for p in problemas:
        print("no se pudo leer —", p, file=sys.stderr)


if __name__ == "__main__":
    main()
