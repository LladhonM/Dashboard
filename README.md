---
title: ¿Conviene comprar para alquilar?
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 8501
pinned: false
short_description: Tablero del TP de Analítica Descriptiva (ITBA), Grupo 2
---

# ¿Conviene comprar para alquilar? · Tablero

Tablero del TP Integrador de 82.04 Analítica Descriptiva (ITBA), Grupo 2. Este repositorio
tiene solo lo que el tablero necesita para publicarse en Hugging Face Spaces. El bloque de
arriba (entre las líneas `---`) es la configuración del Space: no borrarlo.

El código original está en el repositorio del TP, en `Entrega 3/tablero/`. Un cambio en el
tablero se hace allá y se copia acá.

## Contenido

| Ruta | Origen en el repositorio del TP |
|---|---|
| `app.py`, `datos.py` | `Entrega 3/tablero/` (en `datos.py` cambia solo `RAIZ`) |
| `.streamlit/config.toml` | `Entrega 3/tablero/.streamlit/` |
| `src/eda.py`, `src/supuestos.py` | `Entrega 3/src/` |
| `data/processed/`, `data/external/` | `Entrega 3/data/`, solo los archivos que lee el tablero |
| `Dockerfile` | Solo de este repositorio: arma el contenedor del Space |

## Correr en la computadora

```
pip install -r requirements.txt
streamlit run app.py
```
