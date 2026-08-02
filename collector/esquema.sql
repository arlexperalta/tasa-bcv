-- Histórico de la tasa. Dos series con naturalezas distintas y por eso dos tablas:
--
--   bcv  — una fila por fecha-valor. El BCV publica una vez por día hábil y el
--          valor de una fecha-valor ya publicada no cambia nunca. Se puede
--          reconstruir hacia atrás desde los xls del SMC (ver backfill_bcv.py).
--   usdt — una fila por hora. Binance P2P se mueve intradía y NO hay forma de
--          recuperarlo hacia atrás: lo que no se anota hoy se pierde para siempre.

CREATE TABLE IF NOT EXISTS bcv (
  -- día en que la tasa rige (no el día en que se publicó: el BCV publica en la
  -- tarde la que rige mañana, y el viernes la del lunes)
  fecha_valor   TEXT PRIMARY KEY,
  -- venta/ASK es EL número: es el que muestra la app, el que da dolarapi como
  -- "promedio" y el que sale en el home del BCV. Verificado contra los xls.
  usd_venta     REAL NOT NULL,
  usd_compra    REAL,
  eur_venta     REAL,
  eur_compra    REAL,
  fuente        TEXT NOT NULL,   -- 'smc-xls' (autoridad) | 'bcv-home'
  capturado_en  TEXT NOT NULL    -- ISO UTC del momento en que lo anotamos
);

CREATE TABLE IF NOT EXISTS usdt (
  hora          TEXT PRIMARY KEY,  -- ISO UTC truncado a la hora: una fila por hora
  compra        REAL,              -- bid
  venta         REAL,              -- ask
  promedio      REAL NOT NULL,     -- (bid+ask)/2 — lo que la app muestra
  -- timestamp que trae el payload de CriptoYa. Si el proxy sirvió una copia
  -- vieja (cae la fuente), esto lo delata: el promedio sería el mismo de antes.
  fuente_ts     TEXT,
  capturado_en  TEXT NOT NULL
);

-- Bitácora de cada corrida del colector. Es lo que convierte al colector en el
-- vigía de la tarea 4ec212a6: sin esto, una fuente puede morir en silencio.
CREATE TABLE IF NOT EXISTS corridas (
  ts            TEXT PRIMARY KEY,
  bcv_estado    TEXT NOT NULL,   -- ok | falla | viejo
  usdt_estado   TEXT NOT NULL,
  detalle       TEXT
);
