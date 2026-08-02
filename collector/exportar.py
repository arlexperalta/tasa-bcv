#!/usr/bin/env python3
"""Saca el histórico de SQLite a un JSON que sirve el mismo nginx del sitio.

La base vive fuera de la raíz web a propósito (no se publica el archivo crudo);
lo que sale es este JSON, en /opt/tasa/historico.json → /historico.json.

Dos consumidores en mente:
  - el contenido diario (el dato se mueve todos los días y el acumulado es
    material que nadie más tiene publicado);
  - un gráfico dentro de la app, el día que se haga, sin infra nueva.

El USDT se agrega por día (promedio, mínimo, máximo y cuántas muestras lo
sostienen). La hora a hora se queda en SQLite: aquí no aporta y multiplica el
peso por 24.
"""

import argparse
import json
import os
import sqlite3
import tempfile
from datetime import date, datetime, timezone

SALIDA = os.environ.get("TASA_JSON", "/opt/tasa/historico.json")
DB = os.environ.get("TASA_DB", "/opt/tasa-historico/tasa.db")


def variaciones(serie):
    """Cambio porcentual del USD contra el dato de hace N días. Es el insumo
    directo del contenido: "el dólar subió X% en el mes"."""
    if not serie:
        return {}
    por_fecha = {date.fromisoformat(f): v for f, v, _ in serie}
    hasta = max(por_fecha)
    actual = por_fecha[hasta]
    out = {}
    for etiqueta, dias in (("7d", 7), ("30d", 30), ("90d", 90), ("365d", 365)):
        objetivo = hasta.toordinal() - dias
        # El día exacto puede ser feriado o fin de semana: se toma el dato
        # publicado más cercano hacia atrás.
        previas = [d for d in por_fecha if d.toordinal() <= objetivo]
        if not previas:
            continue
        base = por_fecha[max(previas)]
        out[etiqueta] = round((actual / base - 1) * 100, 2)
    enero = [d for d in por_fecha if d.year == hasta.year]
    if enero:
        base = por_fecha[min(enero)]
        out["anio"] = round((actual / base - 1) * 100, 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--salida", default=SALIDA)
    args = ap.parse_args()

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)

    bcv = [
        [f, u, e]
        for f, u, e in con.execute(
            "SELECT fecha_valor, usd_venta, eur_venta FROM bcv ORDER BY fecha_valor"
        )
    ]
    usdt = [
        [f, round(p, 4), round(mn, 4), round(mx, 4), n]
        for f, p, mn, mx, n in con.execute(
            "SELECT substr(hora, 1, 10), avg(promedio), min(promedio), max(promedio), count(*)"
            " FROM usdt GROUP BY 1 ORDER BY 1"
        )
    ]
    ultima_corrida = con.execute(
        "SELECT ts, bcv_estado, usdt_estado FROM corridas ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    con.close()

    doc = {
        "generado": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "fuente": "BCV (tipo de cambio de referencia, columna venta) y Binance P2P vía CriptoYa",
        "nota": (
            "Bolívar digital: la serie arranca en la reconversión del 1-oct-2021. "
            "El BCV solo publica días hábiles; los saltos de 4-5 días son feriados."
        ),
        "bcv": {
            "campos": ["fecha", "usd", "eur"],
            "desde": bcv[0][0] if bcv else None,
            "hasta": bcv[-1][0] if bcv else None,
            "dias": len(bcv),
            "variacion_usd_pct": variaciones(bcv),
            "serie": bcv,
        },
        "usdt": {
            "campos": ["fecha", "promedio", "min", "max", "muestras"],
            "desde": usdt[0][0] if usdt else None,
            "hasta": usdt[-1][0] if usdt else None,
            "dias": len(usdt),
            "serie": usdt,
        },
    }
    if ultima_corrida:
        doc["ultima_corrida"] = {
            "ts": ultima_corrida[0],
            "bcv": ultima_corrida[1],
            "usdt": ultima_corrida[2],
        }

    # Escritura atómica: nginx está sirviendo este archivo mientras se regenera.
    # Sin esto, una petición a mitad de camino se lleva un JSON partido.
    destino = os.path.abspath(args.salida)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(destino), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, destino)

    print(
        f"{destino}: BCV {doc['bcv']['dias']} días ({doc['bcv']['desde']} → {doc['bcv']['hasta']}), "
        f"USDT {doc['usdt']['dias']} días, {os.path.getsize(destino) // 1024} KB"
    )


if __name__ == "__main__":
    main()
