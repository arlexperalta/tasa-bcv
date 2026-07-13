# Tasa BCV

Calculadora de cambio para Venezuela. Convierte bolívares a dólares y euros con la **tasa oficial del BCV**, y USDT con la tasa de **Binance P2P**, en el teléfono, sin fricción.

**En vivo:** [tasa.arlexperalta.com](https://tasa.arlexperalta.com)

## Qué hace

- Trae sola la tasa oficial del BCV de **dólar** y **euro**, y la de **Binance P2P** para USDT, al abrir.
- Convierte en ambos sentidos: escribes en bolívares o en la moneda, y el otro campo se calcula solo.
- Formato venezolano (`1.000.000,00`).
- Tasa **editable a mano** por si prefieres otra, con un toque para volver a la del BCV.
- **Funciona sin internet** con la última tasa guardada.
- Pensada para usarse en el teléfono: campos grandes, lectura clara.

## Cómo funciona

Es una sola página estática, sin backend ni base de datos. Las tasas se piden directo desde el navegador a APIs públicas:

- Dólar BCV: `https://ve.dolarapi.com/v1/dolares/oficial` ([dolarapi.com](https://ve.dolarapi.com))
- Euro BCV: `https://ve.dolarapi.com/v1/euros/oficial` ([dolarapi.com](https://ve.dolarapi.com))
- USDT Binance P2P: `https://criptoya.com/api/binancep2p/USDT/VES/100` ([CriptoYa](https://criptoya.com)) — se muestra el promedio entre compra y venta para órdenes de 100 USDT

La última tasa y la moneda elegida se guardan en `localStorage`, así que si se cae la conexión la calculadora sigue sirviendo con el último valor. Todo el código —HTML, CSS y JavaScript— vive en `index.html`, sin dependencias ni build.

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
