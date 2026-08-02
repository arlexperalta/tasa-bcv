#!/usr/bin/env python3
"""Colector horario del histórico de la tasa. Corre por cron en Contabo.

Dos trabajos en un solo proceso, a propósito:

1. Guardar la serie. El BCV se puede reconstruir hacia atrás desde los xls del
   SMC, pero Binance P2P no: CriptoYa da spot y nada más. Cada hora sin anotar
   es una hora perdida para siempre.

2. Vigilar las fuentes (tarea 4ec212a6). Un proceso que cada hora intenta traer
   las dos tasas y anotar la fila YA ES el vigía: si no puede, avisa. Por eso
   pide por las URL del propio sitio (/api/bcv, /api/usdt) y no directo a las
   fuentes — así vigila el camino real que recorre el usuario, incluido el proxy.

La alerta es por transición y a la SEGUNDA corrida mala seguida (~2h de caída
real). Una falla suelta es ruido: CriptoYa bloquea por IP de vez en cuando y se
recupera solo.
"""

import gzip
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("TASA_BASE", "https://tasa.arlexperalta.com")
DB = os.environ.get("TASA_DB", "/opt/tasa-historico/tasa.db")
ESQUEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "esquema.sql")
ESTADO = os.environ.get("TASA_ESTADO", "/opt/tasa-historico/.estado.json")
TG_CONFIG = "/opt/scripts/health-monitor/health-config.json"
TG_CHAT_FALLBACK = "616781271"

# Umbrales de "viejo". El BCV no publica fines de semana ni feriados: 4 días
# cubre un puente largo sin gritar. El P2P se mueve todo el tiempo; 3h de dato
# congelado significa que el proxy está sirviendo su copia vieja.
BCV_DIAS_MAX = 4
USDT_HORAS_MAX = 3
CORRIDAS_MALAS_PARA_ALERTAR = 2

CARACAS = timezone(timedelta(hours=-4))


def ahora_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.replace(microsecond=0).isoformat()


def pedir(ruta, timeout=20, intentos=2, espera=5):
    """Trae una ruta del sitio, reintentando una vez.

    Pide `identity` explícito y aun así sabe descomprimir: el 2026-08-02 este
    colector falló tres corridas seguidas contra /api/usdt recibiendo un cuerpo
    que empezaba con la firma de gzip y terminaba en JSON plano — dos respuestas
    distintas peleándose el mismo archivo de caché de nginx (ver el comentario de
    /api/usdt en nginx/default.conf). El arreglo de fondo está en el proxy; esto
    es el cinturón por si algún día vuelve a colarse una respuesta comprimida.
    """
    ultimo = None
    for intento in range(intentos):
        try:
            req = urllib.request.Request(
                BASE + ruta,
                headers={
                    "User-Agent": "tasa-historico/1.0",
                    "Cache-Control": "no-store",
                    "Accept-Encoding": "identity",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as res:
                crudo = res.read()
                comprimido = res.headers.get("Content-Encoding", "") == "gzip"
            if comprimido or crudo[:2] == b"\x1f\x8b":
                crudo = gzip.decompress(crudo)
            cuerpo = crudo.decode("utf-8", "replace").strip()
            if not cuerpo:
                raise ValueError(f"{ruta} respondió 200 con cuerpo vacío")
            return cuerpo
        except Exception as e:
            ultimo = e
            if intento + 1 < intentos:
                time.sleep(espera)
    raise ultimo


# --- BCV -------------------------------------------------------------------
# Mismo parseo que hace la app en index.html: la fecha-valor sale de un <meta>
# y las tasas del bloque con id="dolar" / id="euro".

def parsear_bcv(html):
    m_fecha = re.search(r'Fecha Valor:[\s\S]{0,200}?content="(\d{4}-\d{2}-\d{2})', html)

    def num(m):
        if not m:
            return None
        v = float(m.group(1).replace(".", "").replace(",", "."))
        return v if v > 0 else None

    usd = num(re.search(r'id="dolar"[\s\S]{0,800}?strong-tb">\s*([\d.,]+)', html))
    eur = num(re.search(r'id="euro"[\s\S]{0,800}?strong-tb">\s*([\d.,]+)', html))
    if not m_fecha or usd is None:
        raise ValueError("el HTML del BCV no trae fecha-valor o dólar")
    return m_fecha.group(1), usd, eur


def recolectar_bcv(con):
    html = pedir("/api/bcv", timeout=25)
    fecha_valor, usd, eur = parsear_bcv(html)

    # El home del BCV solo publica la venta. Las columnas de compra las llena el
    # backfill desde los xls, que sí las traen; aquí se dejan en NULL.
    con.execute(
        "INSERT OR IGNORE INTO bcv (fecha_valor, usd_venta, eur_venta, fuente, capturado_en)"
        " VALUES (?, ?, ?, 'bcv-home', ?)",
        (fecha_valor, usd, eur, iso(ahora_utc())),
    )

    hoy = datetime.now(CARACAS).date()
    atraso = (hoy - datetime.strptime(fecha_valor, "%Y-%m-%d").date()).days
    if atraso > BCV_DIAS_MAX:
        return "viejo", f"la fecha-valor más nueva es {fecha_valor} ({atraso} días atrás)"
    return "ok", f"fecha-valor {fecha_valor} · USD {usd}"


# --- USDT ------------------------------------------------------------------

def recolectar_usdt(con):
    d = json.loads(pedir("/api/usdt"))
    bid, ask = float(d["bid"]), float(d["ask"])
    promedio = (bid + ask) / 2
    if not promedio > 0:
        raise ValueError("promedio no positivo")

    ahora = ahora_utc()
    hora = iso(ahora.replace(minute=0, second=0, microsecond=0))
    fuente_ts = d.get("time")
    fuente_dt = datetime.fromtimestamp(fuente_ts, timezone.utc) if fuente_ts else None

    con.execute(
        "INSERT OR REPLACE INTO usdt (hora, compra, venta, promedio, fuente_ts, capturado_en)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (hora, bid, ask, promedio, iso(fuente_dt) if fuente_dt else None, iso(ahora)),
    )

    if fuente_dt:
        edad = (ahora - fuente_dt).total_seconds() / 3600
        if edad > USDT_HORAS_MAX:
            return "viejo", f"el dato de CriptoYa tiene {edad:.1f}h (el proxy sirve copia vieja)"
    return "ok", f"promedio {promedio:.2f} Bs"


# --- Alerta ----------------------------------------------------------------

def avisar(texto):
    """Telegram, mismo canal y config que trading-bot-deadman.sh."""
    token, chat = "", TG_CHAT_FALLBACK
    try:
        with open(TG_CONFIG) as f:
            tg = json.load(f).get("telegram", {})
        token = tg.get("bot_token") or ""
        chat_cfg = str(tg.get("chat_id") or "")
        if chat_cfg and "${" not in chat_cfg:
            chat = chat_cfg
    except Exception:
        pass
    if not token:
        print("aviso: sin bot_token, no se pudo notificar", file=sys.stderr)
        return
    datos = json.dumps({"chat_id": chat, "text": texto}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=datos,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        print(f"aviso: falló el envío a Telegram: {e}", file=sys.stderr)


def revisar_transicion(estado_previo, fuente, bien, detalle):
    """Devuelve el texto a enviar, o None si no hay nada que decir.

    Solo habla en los bordes: cuando acumula CORRIDAS_MALAS_PARA_ALERTAR seguidas
    y cuando vuelve. Entre medio se calla, si no el cron avisa cada hora de lo
    mismo y en dos días Arlex silencia el chat.
    """
    previo = estado_previo.get(fuente, {"malas": 0, "avisado": False})
    malas = 0 if bien else previo.get("malas", 0) + 1
    avisado = previo.get("avisado", False)
    texto = None

    if not bien and malas >= CORRIDAS_MALAS_PARA_ALERTAR and not avisado:
        texto = f"tasa: {fuente} lleva {malas} corridas sin dato bueno — {detalle}"
        avisado = True
    elif bien and avisado:
        texto = f"tasa: {fuente} se recuperó — {detalle}"
        avisado = False

    estado_previo[fuente] = {"malas": malas, "avisado": avisado}
    return texto


def main():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB)
    with open(ESQUEMA) as f:
        con.executescript(f.read())

    try:
        with open(ESTADO) as f:
            estado = json.load(f)
    except Exception:
        estado = {}

    resultados = {}
    for nombre, fn in (("bcv", recolectar_bcv), ("usdt", recolectar_usdt)):
        try:
            resultados[nombre] = fn(con)
        except Exception as e:
            resultados[nombre] = ("falla", f"{type(e).__name__}: {e}")

    con.execute(
        "INSERT OR REPLACE INTO corridas (ts, bcv_estado, usdt_estado, detalle) VALUES (?, ?, ?, ?)",
        (
            iso(ahora_utc()),
            resultados["bcv"][0],
            resultados["usdt"][0],
            json.dumps({k: v[1] for k, v in resultados.items()}, ensure_ascii=False),
        ),
    )
    con.commit()
    con.close()

    for nombre, (est, detalle) in resultados.items():
        print(f"{nombre}: {est} — {detalle}")
        texto = revisar_transicion(estado, nombre, est == "ok", detalle)
        if texto:
            avisar(texto)

    with open(ESTADO, "w") as f:
        json.dump(estado, f)

    # Sale distinto de 0 si alguna fuente falló: útil si algún día esto cuelga
    # de un monitor externo en vez del cron pelado.
    return 0 if all(v[0] == "ok" for v in resultados.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
