# Tasa BCV

Calculadora de cambio para Venezuela. Convierte bolívares a dólares y euros con la **tasa oficial del BCV**, y USDT con la tasa de **Binance P2P**, en el teléfono, sin fricción.

**En vivo:** [tasa.arlexperalta.com](https://tasa.arlexperalta.com)

## Qué hace

- Trae sola la tasa oficial del BCV de **dólar** y **euro**, y la de **Binance P2P** para USDT, al abrir.
- Convierte en ambos sentidos: escribes en bolívares o en la moneda, y el otro campo se calcula solo.
- Formato venezolano (`1.000.000,00`).
- Botón para borrar los montos de un toque y empezar de cero.
- **Compartir contextual**: si hay un cálculo en pantalla comparte el cálculo con su tasa y la fecha de esa tasa; si no, comparte la app. Usa la hoja nativa del sistema (`navigator.share`) y cae al portapapeles donde no exista.
- **Tasa del día siguiente**: cuando el BCV ya publicó la de mañana (cada tarde hábil; el viernes, la del lunes), un botón deja ver y calcular con ella y volver a la de hoy.
- **Funciona sin internet** con la última tasa guardada.
- Pensada para usarse en el teléfono: campos grandes, lectura clara.

## Cómo funciona

Es una sola página estática, sin backend ni base de datos. Las tasas se piden desde el navegador a APIs públicas:

- Dólar BCV: `https://ve.dolarapi.com/v1/dolares/oficial` ([dolarapi.com](https://ve.dolarapi.com))
- Euro BCV: `https://ve.dolarapi.com/v1/euros/oficial` ([dolarapi.com](https://ve.dolarapi.com))
- USDT Binance P2P: `/api/usdt`, que el nginx del sitio pasa a `https://criptoya.com/api/binancep2p/USDT/VES/100` ([CriptoYa](https://criptoya.com)) — se muestra el promedio entre compra y venta para órdenes de 100 USDT

**Por qué USDT pasa por el proxy** (2026-07-15): CriptoYa dejó de permitir el fetch desde el navegador (CORS) y bloquea por IP, aunque sí responde server-to-server. Pedirla desde el propio dominio la vuelve same-origin y el CORS deja de aplicar. La config vive en `nginx/default.conf` y cachea 60s (CriptoYa manda `no-store`, que se ignora a propósito para no pegarle a su API en cada visita). El proxy sirve la última copia buena si la fuente cae; el payload trae su propio timestamp, así que la hora que muestra la app es la del dato, no una fresca falsa.

**Lo que se comparte dice de qué día es la tasa** (2026-07-25): el texto no dice "tasa de hoy" sino "Tasa BCV del vie 25 jul". Si el usuario está viendo la tasa del día siguiente, eso es lo que sale en el mensaje. Un cálculo compartido viaja fuera de la app y sobrevive al día en que se hizo; sin la fecha, el que lo recibe no puede saber si sigue vigente.

**El link compartido lleva marca, y la marca no se propaga** (2026-08-20): el mensaje sale con `?ref=c`, y al abrirlo la app emite `llegada_compartida` y borra el parámetro de la barra. Es la única forma de contar al que LLEGA: un link pegado en WhatsApp o Telegram se abre sin referrer, así que esa visita era indistinguible de la de quien escribió el dominio a mano. Dos límites que van escritos también en el código: la serie **empieza el 20-ago-2026** y no se compara con nada anterior, y cuenta **solo el primer salto** —quien llega por un reenvío y comparte a su vez manda el link limpio, porque el mensaje sale con `origin`, sin query—, así que el número es un piso y nunca un total.

**Cuando no hay tasa, no hay número.** Si una fuente no carga, la calculadora borra el monto convertido y avisa (`sin datos · actualiza`) en vez de dejar el resultado calculado con la tasa de otra moneda. Antes no lo hacía: al cambiar a USDT con la fuente caída, la pantalla mostraba un monto de dólar rotulado USDT. Un número equivocado con la etiqueta correcta es peor que ningún número.

La última tasa y la moneda elegida se guardan en `localStorage`, así que si se cae la conexión la calculadora sigue sirviendo con el último valor. Todo el código —HTML, CSS y JavaScript— vive en `index.html`, sin dependencias ni build.

## Histórico

La app no guardaba nada: cada tasa vivía solo en el `localStorage` del visitante y se pisaba al día siguiente. Desde el 2026-08-02 hay una serie propia en `collector/`, y el mismo proceso que la escribe vigila las fuentes.

- **`recolectar.py`** — cron horario en Contabo. Pide por `/api/bcv` y `/api/usdt` **del propio sitio**, no directo a las fuentes: así vigila el camino real que recorre el usuario, proxy incluido. Anota la fila en `/opt/tasa-historico/tasa.db` (SQLite) y avisa por Telegram cuando una fuente lleva **dos corridas seguidas** sin dato bueno, y otra vez cuando vuelve.
- **`backfill_bcv.py`** — corrida única. El BCV publica su tipo de cambio de referencia en xls trimestrales con una hoja por día hábil, y la columna de **venta** es exactamente el número que muestra la app (verificado contra el home del BCV y contra el `promedio` de dolarapi). O sea que el histórico del BCV no se empieza a guardar: se importa. Cargados **1.160 días, del 2021-10-04 al 2026-08-03**.
- **`exportar.py`** — cron horario. Saca la serie a `/historico.json` (~40 KB, ~12 gzipeado): días del BCV, agregado diario del USDT y la variación del dólar a 7/30/90/365 días. La base cruda se queda fuera de la raíz web.

**Por qué el USDT es el urgente y el BCV no.** El BCV está archivado por el propio BCV y se puede traer cuando sea. Binance P2P no: CriptoYa da spot y ya. La hora que no se anota se pierde para siempre, y es la serie que se mueve intradía y muestra la brecha contra la oficial.

Dos trampas que costaron sangre y por eso están escritas en el código:

- **La reconversión monetaria del 1-oct-2021** (1.000.000 Bs → 1 Bs). El Q1-2021 trae el dólar a 2.070.854 y el Q4 a 4,17. La serie arranca en la reconversión y lo anterior se descarta por fecha, no por archivo: un archivo de Q4 puede traer hojas de septiembre.
- **Los nombres de archivo del BCV mienten.** `2_1_2c23_smc.xls` debería ser jul-sep 2023 y trae dos hojas de octubre; los 60 días de ese trimestre viven en `2_1_2c23_smc_60.xls`, que solo aparece en la página 2 del listado. Adivinar el patrón dejaba un hueco de 91 días sin avisar a nadie. Por eso el backfill raspa el listado además de probar el patrón, y **canta los huecos** al terminar: una serie con agujeros callados es peor que no tenerla, porque el gráfico dibuja una recta donde no hubo dato.

Los saltos de 4-5 días que quedan son feriados (carnaval, semana santa, Carabobo). El BCV no publica fines de semana ni días no hábiles.

### El bug que el vigía encontró el primer día

A las tres horas de instalarse, el colector alertó: `/api/usdt` fallaba en cada corrida. El cuerpo llegaba así —

```
(\x1f\x8b... X\x8e d{"ask":845,"totalAbidBime":1785696467}
```

`\x1f\x8b` es la firma de gzip, y `"totalAbidBime"` no es JSON roto: son **`"totalAsk"`, `"bid"` y `"time"` de dos respuestas distintas pisadas una encima de la otra**.

CriptoYa manda `Vary: Accept-Encoding` y responde comprimido o plano según lo que pida el cliente. Nuestro proxy ignoraba ese `Vary` y cacheaba todo bajo una sola clave (`usdt-ves-100`), así que la respuesta gzipeada de un navegador y la plana de un cliente sin gzip terminaban compitiendo por **el mismo archivo de caché**. Quien leía justo durante la sobreescritura se llevaba un cuerpo partido: cabeza de una, cola de la otra.

Para el usuario eso era USDT en `sin datos · actualiza` sin razón aparente, intermitente y por eso invisible durante semanas. Con ~1.500 personas al mes, le tocó a gente real.

El arreglo es `proxy_set_header Accept-Encoding "";` en `/api/usdt`: si la fuente responde siempre plano, existe una sola variante posible y la clave única vuelve a ser correcta. `/api/bcv` ya lo hacía por otro motivo. Verificado con 40 peticiones alternando clientes con y sin gzip a lo largo de dos vencimientos y medio de caché: 0 fallos, contra 3 de 3 corridas fallando antes.

El colector además pide `identity` explícito y descomprime si igual le llega gzip. El arreglo de fondo está en el proxy; eso es el cinturón.

`backfill_bcv.py` necesita `xlrd`, que Contabo no tiene: corre en la torre y la base viaja por `scp`.

## Correr localmente

No hay nada que instalar. Abre `index.html` en el navegador, o levanta un servidor estático:

```bash
python3 -m http.server 8000
# luego abre http://localhost:8000
```

## Despliegue

Al ser un solo archivo estático, se sirve desde cualquier hosting. La versión en vivo corre en un contenedor `nginx:alpine` detrás de Nginx Proxy Manager con SSL. Actualizar es copiar el `index.html` al servidor; no hay paso de compilación.

## Diseño

Gris neutro medio oscuro con la firma visual de la marca personal de Arlex Peralta ("Orden del Caos"): rojo OMA como único acento, Inter Tight en los números y JetBrains Mono en las etiquetas.

---

Hecho en Venezuela por [Arlex Peralta](https://arlexperalta.com).
