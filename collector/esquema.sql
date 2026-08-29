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

-- ---- micro-encuesta de uso (29-ago-2026) -----------------------------------
-- Una pregunta dentro de la app, una vez por dispositivo: "¿Para qué usaste la
-- tasa ahorita?". No hay servidor que reciba: nginx anota la línea en su log y
-- ingerir_encuesta.py la trae aquí. Tres tablas y no una, a propósito.

-- La vista va en la MISMA tabla que la respuesta porque es su denominador. Sin
-- ella, un resultado flojo no se puede leer: "la vieron y no les interesó" y
-- "no la vieron" darían el mismo número, y solo el primero cierra la puerta.
CREATE TABLE IF NOT EXISTS encuesta (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        TEXT NOT NULL,     -- ISO del momento en que nginx lo registró
  evento    TEXT NOT NULL,     -- vista | respuesta | cerrada
  opcion    INTEGER,           -- 1..5, solo en 'respuesta'
  -- En qué lugar de la lista salió la opción marcada (1..5) y el barajado
  -- completo de esa sesión. Las opciones salen en orden aleatorio para que la
  -- primera no se lleve votos por estar primera; esto es lo que permite
  -- VERIFICAR después que no hubo sesgo de posición, en vez de suponerlo.
  posicion  INTEGER,
  orden     TEXT
);

-- Texto libre de quien marcó "Otra cosa". Va aparte porque llega en un envío
-- distinto: la opción se manda al tocarla y el texto solo si lo escriben, así
-- que quien marca la 5 y abandona igual cuenta como respuesta.
CREATE TABLE IF NOT EXISTS encuesta_texto (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  ts     TEXT NOT NULL,
  texto  TEXT NOT NULL
);

-- Correos de quien marcó la 3 o la 4 y quiso probar la app de Android.
-- SIN vínculo con la respuesta, a propósito: no se pierde nada porque solo ve
-- ese campo quien marcó 3 o 4 —la lista ya nace filtrada—, y guardar el vínculo
-- convertiría una respuesta anónima en una identificada.
-- UNIQUE para que un doble envío no infle la lista de testers.
CREATE TABLE IF NOT EXISTS encuesta_correo (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  ts      TEXT NOT NULL,
  correo  TEXT NOT NULL UNIQUE
);
