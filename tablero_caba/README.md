# ¿Conviene comprar para alquilar? · Tablero

Tablero del TP Integrador de 82.04 Analítica Descriptiva (ITBA), Grupo 2. Este repositorio
tiene solo lo que el tablero necesita para publicarse en Streamlit Community Cloud.

El código original está en el repositorio del TP, en `Entrega 3/tablero/`. Un cambio en el
tablero se hace allá y se copia acá.

## Contenido

| Ruta | Origen en el repositorio del TP |
|---|---|
| `app.py`, `datos.py` | `Entrega 3/tablero/` (en `datos.py` cambia solo `RAIZ`) |
| `.streamlit/config.toml` | `Entrega 3/tablero/.streamlit/` |
| `src/eda.py`, `src/supuestos.py` | `Entrega 3/src/` |
| `data/processed/`, `data/external/` | `Entrega 3/data/`, solo los archivos que lee el tablero |

## Correr en la computadora

```
pip install -r requirements.txt
streamlit run app.py
```

## Publicar en Streamlit Community Cloud

Archivo principal: `app.py`. Versión de Python: 3.13 (en "Advanced settings").
