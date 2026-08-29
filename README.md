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

**Calcular con la tasa de un día pasado** (2026-08-20): la etiqueta que declara qué tasa estás viendo (`Tasa del día · BCV`) es el control para cambiarla — se toca y abre una hoja con los siete días recientes y un `<input type="date">` nativo para ir más atrás, hasta el 4-oct-2021. Idea de un usuario, con su caso de uso textual: *"cuánto me costó realmente algo hace 3 días"*. Eso es **pasado reciente y no archivo**, y por eso la puerta son siete días en una tira y no un calendario: nadie piensa "17 de agosto", piensa "el lunes". La tira corre en orden cronológico con hoy a la derecha, igual que la gráfica del histórico y que las flechas ‹ ›.

Cuatro decisiones que no son de conveniencia y por eso están en el código:

- **El modo pasado no persiste.** Al reabrir la app siempre es hoy. Un estado en el que la pantalla muestra una tasa que no es la vigente no se hereda entre sesiones: así es como alguien calcularía mal con toda confianza. Por lo mismo el punto en vivo se apaga, la barra va en superficie invertida y "Hoy" está siempre a un toque.
- **Fin de semana y feriados se pueden elegir.** El BCV solo publica días hábiles: de los 1.782 días del rango, 609 no tienen fila y 508 son fin de semana. Pero la tasa vigente un sábado existe —la del último día hábil, que es la que se usa para facturar— así que la app la aplica y dice cuál es. Decir "no hay dato" ahí sería falso, y el fin de semana es justo cuando se compra.
- **USDT no retrocede a otro día.** Binance opera todos los días, así que un día que falta es un día que no se anotó, no un día sin mercado. Antes del 2-ago-2026 no hay serie y ahí no hay número: ni la tasa ni el monto derivado.
- **Un día pedido fuera de la serie no se corrige al más cercano.** Se muestra el día que se pidió y el aviso dice que ahí no hay dato. Llevar en silencio a otra fecha responde una pregunta distinta a la que se hizo.

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

## La pregunta

Desde el 29-ago-2026 la app hace **una pregunta, una sola vez por dispositivo**: *"¿Para qué usaste la tasa ahorita?"*, con cinco opciones en orden aleatorio. Existe porque tasa lleva un año con miles de visitas al mes y a esa gente no se le ha preguntado nunca para qué usa esto. Se sabe "precios en tienda" y "cambiar efectivo" porque alguien lo dijo suelto; de ahí en adelante era suposición.

**El umbral está escrito antes de mirar los números, y eso es lo único que hace honesta la prueba:** si las opciones 3 y 4 —cobrarle a un cliente, cuadrar cuentas— no llegan juntas al **10% de las respuestas**, no hay un negocio ahí y la puerta se cierra.

**El denominador son las respuestas, nunca las impresiones.** Desde que se cuenta la impresión hay dos denominadores posibles en la misma base, y calcular ese 10% sobre impresiones cerraría la puerta por error casi seguro. Las impresiones sirven para otra cosa —distinguir *"no la vieron"* de *"la vieron y no les interesó"*—: son diagnóstico de la pieza, no medida del interés, y no entran en el veredicto.

`ingerir_encuesta.py --resumen` exige **tres condiciones** para dar veredicto, y las tres solo pueden retenerlo, nunca darlo por bueno de más:

1. **200 respuestas, o el 19-sep-2026.** Leer a medio camino y ajustar el umbral después es lo que convierte una prueba en una excusa.
2. **Al menos 50 respuestas.** Con menos, el 10% son cinco personas y eso no distingue señal de ruido; a 200 son veinte y sí. Por debajo no cierra *ni abre*: la lectura es "no alcanzó para saber".
3. **Tasa de respuesta del 5% o más.** Si responde casi nadie de quien la ve, lo que falla es la pieza —no se ve bien o estorba—, no la hipótesis, y lo que se revisa es la pieza. Esta condición solo existe gracias al conteo de impresiones.

**El borde se acata, no se prorroga.** Con 50 respuestas o más y una tasa de respuesta sana, un 9% no es "no alcanzó para saber": es que **no pasa**. Va escrito en el script porque es por donde se colaría la primera lectura floja.

**Y si no hay veredicto, hay diagnóstico, no prórroga a ciegas.** Las impresiones dicen de qué murió: menos de 400, el problema es el filtro o el tráfico y no sabemos nada de la gente todavía; 400 o más con tasa bajo el 5%, el problema es la pieza. Se nombra la causa, se corrige **esa** y solo esa —si fue el filtro, se afloja lo mínimo, de "segunda o tercera visita" a "segunda"; si fue la pieza, se cambia **una** cosa, no tres— y se corre **una sola prórroga, hasta el 10-oct-2026**. Nunca se toca "una vez por dispositivo", ni el no-modal, ni la quietud: esas tres protegen la app y valen más que esta prueba.

**La segunda prórroga no existe**, y no solo por método: mientras esto corre, el cruce comercial sigue cediendo el puesto. Seis semanas ya es caro; nueve no se paga.

**El silencio también es un resultado.** Si el 10-oct, tras seis semanas y dos configuraciones sobre ~3.000 sesiones al mes, no se juntaron 50 respuestas, eso deja de ser un no-resultado y pasa a ser *el* resultado: esta población es **tráfico, no público**. Gente que abre una calculadora, resuelve su cuenta y se va. Si no contestan una pregunta de un toque dentro de algo que ya usan y les gusta, no van a comprar nada tampoco. Cierra "monetizar la audiencia de tasa" con evidencia en vez de opinión, y ahorra los meses que costaría descubrirlo construyendo.

Que el 19-sep caiga en "sin veredicto" es **lo esperable**, no un fracaso: con "una vez por dispositivo" y "nunca en la primera visita", el universo real de impresiones es mucho menor que las 3.000 sesiones. Por eso la prórroga está escrita desde ahora y no se improvisa ese día.

Cinco reglas que están en el código y no son de conveniencia:

- **Aparece después del cálculo, nunca al abrir, y nunca tapando nada.** No es modal y no hay que cerrarla para seguir usando la app. Como la calculadora es bidireccional y en vivo, "hizo su cálculo" no existe como momento: lo que se detecta es la **quietud** —monto válido en los dos campos y tres segundos sin tocar nada—, que es la firma de "ya leyó el número".
- **Una vez por dispositivo.** Si la ignoran o la cierran, no vuelve nunca.
- **Nunca en la primera visita.** Quien ya tiene tasas guardadas en `localStorage` cuenta como recurrente desde el primer día: la huella de haber estado aquí ya existía en el teléfono de la gente, y empezar un contador desde cero habría dejado la muestra dos semanas atrás contra un reloj de tres.
- **Le cede el puesto al cruce comercial en vez de sumarse a él**, y no se lo devuelve en esa sesión. Dos cajas seguidas pidiendo algo es exactamente lo que esta app no es, y si el cruce reapareciera justo después de que alguien respondió se leería como cambalache. Vuelve en la visita siguiente, donde nadie nota que hubo un intercambio. **Es un costo aceptado, no gratis:** ese cruce es la mayor fuente de tráfico de arlexperalta.com (56 llegadas medidas) y la única puerta comercial de tasa que funciona. Si durante la prueba el tráfico al sitio cae, el precio es este y hay que atribuirlo aquí y no a otra cosa.
- **El correo va en su propia tabla, sin vínculo con la respuesta.** No se pierde nada: solo ve ese campo quien marcó la 3 o la 4, así que la lista ya nace filtrada. Guardar el vínculo no aportaría y convertiría una respuesta anónima en una identificada.

**Se cuenta la impresión, no solo la respuesta**, y va a la misma base. Es el denominador: sin él, un resultado flojo no se puede leer, porque *"la vieron y no les interesó"* y *"no la vieron"* darían el mismo número y solo el primero cierra la puerta. El observador de visibilidad no dispara con la pestaña en segundo plano, así que responder o cerrar marcan la vista también — quien responde, vio.

**Y se guarda en qué posición salió la opción marcada**, más el barajado completo de esa sesión. El orden es aleatorio para que la primera opción no se lleve votos por estar primera; anotar la posición es lo que permite **verificar** después que no hubo sesgo, en vez de suponerlo.

### Dónde aterriza, y por qué no hay un servicio nuevo

En tasa no había nada escuchando: nginx sirve estático y proxea, y el colector es un cron que **sale** a buscar. Levantar un servicio para recoger 200 respuestas sería meterle al único proyecto que funciona una pieza más que vigilar y que se puede caer.

Así que `/api/encuesta` **no procesa nada**: anota la línea en su propio log y contesta `204`. No tiene forma de fallar porque no ejecuta código. `collector/ingerir_encuesta.py` la trae a SQLite en la corrida horaria, llevando offset e inode para no perder ni repetir líneas, drenando el rotado antes de saltar al archivo nuevo y descartando la última línea si nginx la está escribiendo todavía — la misma clase de error que el cuerpo partido del `/api/usdt` de agosto: leer algo mientras alguien lo escribe.

Lo que cuesta: el dato pasa por un archivo. **`/var/log/tasa` tiene que existir antes de arrancar el contenedor** (`mkdir -p` en el host y bind mount). Si nginx no puede abrir su log no arranca, y eso no es la encuesta caída, es el sitio caído.

```bash
ingerir_encuesta.py              # cron horario, al lado de recolectar.py
ingerir_encuesta.py --resumen    # lee el resultado
```

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
