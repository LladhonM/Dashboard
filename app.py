#!/usr/bin/env python
"""
app.py — Tablero: ¿conviene comprar para alquilar, y si compro, que?

Solo arma la interfaz; la carga, los filtros y las medianas estan en datos.py.
Diseño en data/processed/DISENO_TABLERO.md; datos en GUIA_TABLERO.md.

Uso, desde Entrega 3/tablero/:
    streamlit run app.py
"""

import html
from urllib.parse import quote

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import datos as T
import eda
import supuestos as S

PISO, TECHO = S.RETORNO_MINIMO_BANDA
C = T.COLORES
TODOS = "todos"            # None en un selectbox es "sin eleccion"; por eso un valor propio
MIN_CONFIABLE = 30          # menos propiedades: la mediana es poco confiable
METRICAS = {"Neta": ("rent_neta_pct", "Rentabilidad neta (% anual)"),
            "TIR 5 años": ("tir_5a_pct", "TIR a 5 años, con costos de entrada (% anual)")}
FUENTE = "IBM Plex Sans, sans-serif"      # la del tema (.streamlit/config.toml)
TIPOS_CORTOS = {**T.TIPOS, "departamento": "Depto.", TODOS: "Todos"}
AMBIENTES = ["1", "2", "3", "4", "5+"]    # "5+" junta los de 5 ambientes o mas

# El tamaño general sale de theme.baseFontSize (.streamlit/config.toml): los estilos van en rem
# y el ancho inicial de la barra lateral y las alturas de Plotly, que son en px, se escalan con
# esta proporcion.
ESCALA = (st.get_option("theme.baseFontSize") or 16) / 16
st.set_page_config(page_title="¿Conviene comprar para alquilar?", layout="wide",
                   initial_sidebar_state=round(292 * ESCALA))


@st.cache_data
def cargar():
    return T.cargar()


@st.cache_data
def cargar_ranking():
    return T.cargar_ranking(cargar())


def num(x: float, dec: int = 0) -> str:
    """Formato argentino: punto de miles, coma decimal."""
    return f"{x:,.{dec}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def pct(x: float, dec: int = 2) -> str:
    return f"{num(x, dec)}%"


def rgba(hex_color: str, alfa: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alfa})"


def rango(texto: str) -> str:
    """Rotulo de un rango de superficie o antiguedad: 'hasta 35' -> '≤ 35', '1-5' -> '1–5'."""
    return texto.replace("hasta ", "≤ ").replace("-", "–").capitalize()


def icono(trazos: str, color: str, tam: int = 16) -> str:
    """Icono de trazo como imagen: st.html limpia el HTML con DOMPurify y descarta el <svg> en linea."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{trazos}</svg>')
    return f'<img src="data:image/svg+xml,{quote(svg)}" alt="" width="{tam}" height="{tam}">'


INFO = icono('<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>', C["texto_2"])
ALERTA = icono('<path d="M12 3 2 21h20L12 3z"/><path d="M12 10v4"/><path d="M12 17h.01"/>', "#8A5F0E", 18)
CASA = icono('<path d="M4 11.5 12 5l8 6.5"/><path d="M6.5 10v9h11v-9"/><path d="M10 19v-5h4v5"/>', C["texto"], 22)


# --- Estado de los filtros --------------------------------------------------------
def valores_por_defecto() -> dict:
    f = T.Filtros()
    desde, hasta = (int(v) for v in f.presupuesto)
    return {"desde": desde, "hasta": hasta, "tipo": f.tipo,
            "comunas": [], "barrios": [], "ambientes": [], "superficies": [],
            "antiguedades": [], "metrica": "Neta"}


def restablecer() -> None:
    for clave, valor in valores_por_defecto().items():
        st.session_state[clave] = valor


df = cargar()
for clave, valor in valores_por_defecto().items():
    st.session_state.setdefault(clave, valor)
st.session_state.setdefault("seleccion", None)     # id_aviso elegido en la pestana 3
# Streamlit no deja escribir la seleccion de una tabla o un grafico: para vaciar uno se le
# cambia la key. La version de cada uno va en su key.
st.session_state.setdefault("version_p1", 0)
st.session_state.setdefault("version_p2", 0)


def clave(widget: str) -> str:
    return f"{widget}_{st.session_state['version_' + widget[-2:]]}"


def elegir(id_aviso, vaciar: tuple) -> None:
    """Fija (o borra, con None) la seleccion y vacia los widgets indicados."""
    st.session_state["seleccion"] = id_aviso
    for w in vaciar:
        st.session_state[f"version_{w}"] += 1


def elegir_de_p1() -> None:
    filas = st.session_state[clave("tabla_p1")].selection.rows
    elegir(st.session_state["_ids_p1"][filas[0]] if filas else None, vaciar=("p2",))


def elegir_de_p2() -> None:
    # Solo cuenta la traza de las barras (la 0). Un clic afuera, un doble clic o un clic
    # sobre la barra ya elegida deseleccionan.
    puntos = [p for p in st.session_state[clave("grafico_p2")].selection.points
              if p.get("curve_number") == 0]
    nueva = st.session_state["_ids_p2"][puntos[0]["point_index"]] if puntos else None
    if nueva == st.session_state["seleccion"]:
        nueva = None
    # Tambien se rehace el grafico: si no, Plotly suma su propio atenuado de seleccion al nuestro.
    elegir(nueva, vaciar=("p1", "p2"))


def ambientes_elegidos(elegidos: list, opciones: list) -> tuple:
    """Valores de `ambientes` para el filtro: '5+' son todos los de 5 o mas."""
    valores = []
    for a in elegidos:
        valores += [v for v in opciones if v >= 5] if a == "5+" else [float(a)]
    return tuple(valores)


# --- Barra lateral ----------------------------------------------------------------
MARCA = (f'<div class="marca"><div class="marca-icono">{CASA}</div><div><div class="marca-nombre">'
         'Comprar para alquilar</div><div class="marca-sub">CABA · Grupo 2 · ITBA</div></div></div>'
         '<p class="rotulo">Filtros</p>')

with st.sidebar:
    st.html(MARCA)
    paso = 5_000
    lo = int(df["venta_usd"].min()) // paso * paso
    hi = -(-int(df["venta_usd"].max()) // paso) * paso
    desde, hasta = st.columns(2)
    desde.number_input("Desde (USD)", min_value=lo, max_value=hi, step=paso, key="desde", format="%d")
    hasta.number_input("Hasta (USD)", min_value=lo, max_value=hi, step=paso, key="hasta", format="%d")
    st.segmented_control("Tipo", [*T.TIPOS, TODOS], key="tipo", required=True, width="stretch",
                         format_func=TIPOS_CORTOS.get)
    comuna, barrio = st.columns(2)
    comuna.multiselect("Comuna", T.opciones(df, "comuna"), key="comunas",
                       format_func=lambda c: f"Comuna {c}", placeholder="Todas")
    # El barrio se acota por la comuna: se descartan los elegidos que quedaron afuera.
    barrios = T.barrios_de(df, tuple(st.session_state["comunas"]))
    st.session_state["barrios"] = [b for b in st.session_state["barrios"] if b in barrios]
    barrio.multiselect("Barrio", barrios, key="barrios", format_func=eda.nombre_barrio,
                       placeholder="Todos")
    st.pills("Ambientes", AMBIENTES, selection_mode="multi", key="ambientes", width="stretch")
    st.pills("Superficie (m²)", T.opciones(df, "superficie_rango"), selection_mode="multi",
             key="superficies", format_func=rango, width="stretch")
    st.pills("Antigüedad (años)", T.opciones(df, "antiguedad_rango"), selection_mode="multi",
             key="antiguedades", format_func=rango, width="stretch")
    st.segmented_control("Métrica", list(METRICAS), key="metrica", required=True, width="stretch")
    st.button("Restablecer filtros", icon=":material/restart_alt:", on_click=restablecer, width="stretch")
    st.html(f'<div class="banda-clave"><div class="banda-titulo"><span class="banda-muestra"></span>'
            f'Banda de retorno mínimo</div><div class="banda-valor">{pct(PISO)} – {pct(TECHO)} anual en USD</div>'
            '<div class="banda-nota">ON de YPF 2031 y Pampa 2037. Es la vara fija de todos los gráficos, '
            'no un filtro.</div></div>')

ss = st.session_state
filtros = T.Filtros(presupuesto=tuple(sorted((ss["desde"], ss["hasta"]))),
                    tipo=None if ss["tipo"] == TODOS else ss["tipo"], comunas=tuple(ss["comunas"]),
                    barrios=tuple(ss["barrios"]),
                    ambientes=ambientes_elegidos(ss["ambientes"], T.opciones(df, "ambientes")),
                    superficies=tuple(ss["superficies"]), antiguedades=tuple(ss["antiguedades"]))
vista = T.filtrar(df, filtros)


# --- Estilos ----------------------------------------------------------------------
st.markdown(f"""
<style>
.block-container {{ padding-top: 1.75rem; padding-bottom: 2rem; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stAppDeployButton"] {{ display: none; }}
.stApp {{ font-variant-numeric: tabular-nums; }}
/* Tarjetas: los contenedores con borde van en blanco sobre el fondo gris. */
div[class*="st-key-tarjeta"] {{ background: {C["fondo"]}; border-radius: 1rem; }}
/* Barra lateral */
.marca {{ display: flex; align-items: center; gap: 0.75rem; padding-bottom: 1.125rem;
          border-bottom: 1px solid #474C59; }}
.marca-icono {{ width: 2.25rem; height: 2.25rem; border-radius: 0.625rem; background: #C5D5EA; flex: none;
               display: flex; align-items: center; justify-content: center; }}
.marca-nombre {{ font-size: 0.9375rem; font-weight: 600; color: #FFFFFF; }}
.marca-sub {{ font-size: 0.75rem; color: #C9CED8; }}
/* Cuatro tipos en una sola linea del ancho de la barra lateral. */
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button {{ padding-left: 0.375rem; padding-right: 0.375rem; }}
.rotulo {{ font-size: 0.6875rem; font-weight: 500; letter-spacing: 0.1em; text-transform: uppercase;
           color: #AEB4C2; margin: 0.375rem 0 0; }}
.banda-clave {{ background: #3A3F4B; border-radius: 0.75rem; padding: 0.875rem 1rem; margin-top: 0.5rem; }}
.banda-titulo {{ display: flex; align-items: center; gap: 0.625rem; font-size: 0.8125rem; font-weight: 600;
                 color: #FFFFFF; }}
.banda-muestra {{ width: 1.75rem; height: 0.75rem; border-radius: 3px; background: {C["acento"]}; flex: none; }}
.banda-valor {{ font-size: 0.8125rem; font-weight: 500; color: #F1F3F7; margin: 0.375rem 0 0.25rem; }}
.banda-nota {{ font-size: 0.75rem; line-height: 1.45; color: #C9CED8; }}
/* Encabezado */
.cabecera {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end;
             gap: 1rem 2rem; }}
.cabecera h1 {{ font-size: 2.1rem; line-height: 1.15; font-weight: 700; letter-spacing: -0.02em;
                margin: 0 0 0.375rem; padding: 0; }}
.cabecera p {{ margin: 0; font-size: 0.9375rem; color: {C["texto_2"]}; }}
.contador {{ display: flex; flex-direction: column; gap: 0.375rem; flex: 0 1 17.5rem; min-width: 13.75rem;
             font-size: 0.9375rem; }}
.contador b {{ font-weight: 600; }}
.contador .gris {{ color: {C["texto_2"]}; }}
.contador .barra {{ height: 0.375rem; background: {C["borde"]}; border-radius: 3px; overflow: hidden; }}
.contador .barra div {{ height: 100%; background: {C["texto"]}; border-radius: 3px; }}
.contador .pie {{ font-size: 0.75rem; color: {C["texto_2"]}; }}
.st-key-limitaciones button {{ border-radius: 62.4375rem; background: {C["fondo"]}; }}
/* Ayuda: el atributo title tarda, no sale con clic ni en pantallas tactiles. */
.tip {{ display: inline-flex; color: {C["texto_2"]}; cursor: help; position: relative; outline: none; }}
.tip:hover::after, .tip:focus::after {{
    content: attr(data-tip); position: absolute; right: 0; top: calc(100% + 0.375rem); z-index: 1000;
    width: 16.25rem; padding: 0.5rem 0.7rem; border-radius: 0.5rem; background: {C["texto"]}; color: #FFFFFF;
    font-size: 0.75rem; font-weight: 400; line-height: 1.4; white-space: normal;
    box-shadow: 0 2px 0.5rem rgba(0,0,0,0.15); }}
.tip:focus {{ box-shadow: 0 0 0 2px {C["principal"]}; border-radius: 50%; }}
/* Pestana 1 */
.lectura {{ background: {C["texto"]}; color: #FFFFFF; border-radius: 1rem; padding: 1.375rem 1.5rem;
            min-height: 13.25rem; box-sizing: border-box; display: flex; flex-direction: column; gap: 0.875rem; }}
.lectura .frase {{ margin: 0; font-size: 1.3125rem; line-height: 1.3; font-weight: 600; }}
.lectura em {{ font-style: normal; color: {C["acento"]}; }}
.lectura .leyenda {{ display: flex; flex-wrap: wrap; gap: 0.375rem 1.125rem; font-size: 0.75rem; color: #DDE2EA; }}
.lectura .leyenda span {{ display: inline-flex; align-items: center; gap: 0.375rem; }}
.kpi {{ background: {C["fondo"]}; border: 1px solid {C["borde"]}; border-radius: 1rem; padding: 1.25rem;
        min-height: 13.25rem; box-sizing: border-box; display: flex; flex-direction: column; gap: 0.625rem; }}
.kpi-cab {{ display: flex; justify-content: space-between; align-items: center; font-size: 0.8125rem;
            font-weight: 500; color: {C["texto_2"]}; }}
.kpi-valor {{ font-size: 2.25rem; line-height: 1; font-weight: 600; letter-spacing: -0.02em; }}
.kpi-sub {{ font-size: 0.8125rem; color: {C["texto_2"]}; }}
.escala {{ position: relative; height: 0.875rem; margin-top: auto; }}
.escala > div {{ position: absolute; }}
.marcas {{ position: relative; height: 1rem; font-size: 0.6875rem; color: #AEB4C2; }}
.marcas span {{ position: absolute; transform: translateX(-50%); }}
.etapas {{ display: flex; flex-direction: column; gap: 1.25rem; margin-top: 0.75rem; }}
.etapa-cab {{ display: flex; justify-content: space-between; align-items: baseline; gap: 0.75rem;
              font-size: 0.875rem; font-weight: 500; margin-bottom: 0.5rem; }}
.etapa-cab .cifra {{ font-size: 0.8125rem; font-weight: 400; white-space: nowrap; }}
.etapa-cab .cifra b {{ font-weight: 600; }}
.pista {{ height: 0.75rem; background: #EEF1F6; border-radius: 0.375rem; overflow: hidden; }}
.pista div {{ height: 100%; border-radius: 0.375rem; }}
.aviso {{ display: flex; gap: 0.625rem; align-items: flex-start; background: #FDF6E7; border: 1px solid #F1DDB0;
          border-radius: 0.75rem; padding: 0.75rem 0.875rem; font-size: 0.8125rem; line-height: 1.45; margin: 1rem 0 0.25rem; }}
.aviso svg {{ flex: none; margin-top: 1px; }}
/* Pestana 2 */
.panel {{ display: flex; flex-direction: column; gap: 0.75rem; font-size: 0.8125rem; }}
.panel .rotulo {{ color: {C["texto_2"]}; margin: 0; }}
.panel hr {{ border: 0; border-top: 1px solid #E8ECF2; margin: 0.625rem 0; }}
.apilada {{ display: flex; height: 0.625rem; border-radius: 0.3125rem; overflow: hidden; gap: 2px; }}
.fila-leyenda {{ display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; }}
.fila-leyenda span:first-child {{ display: inline-flex; align-items: center; gap: 0.5rem; }}
.fila-leyenda > span:last-child {{ white-space: nowrap; }}
.punto {{ width: 0.625rem; height: 0.625rem; border-radius: 50%; flex: none; }}
.fila-barrio {{ display: grid; grid-template-columns: 7rem minmax(0, 1fr) 1.75rem; align-items: center; gap: 0.625rem; }}
.fila-barrio .pista {{ height: 0.5rem; background: #F3EEE2; }}
.fila-barrio b {{ font-weight: 500; text-align: right; }}
.nota {{ font-size: 0.75rem; color: {C["texto_2"]}; }}
.dato {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.25rem 0.75rem; margin: 2px 0 0.375rem; }}
.dato-valor {{ font-size: 1.875rem; font-weight: 600; letter-spacing: -0.02em; }}
.dato-sub {{ font-size: 0.8125rem; line-height: 1.4; color: {C["texto_2"]}; flex: 1 1 12.5rem; }}
/* Pestana 3 */
.ficha-cab {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 0.5rem 1rem; }}
.ficha-titulo {{ font-size: 1.0625rem; line-height: 1.3; font-weight: 600; margin: 0 0 0.25rem; }}
.ficha-boton {{ min-height: 2.5rem; display: inline-flex; align-items: center; gap: 0.375rem; padding: 0 0.875rem;
                border-radius: 0.625rem; border: 1px solid #D5DCE6; text-decoration: none; font-size: 0.8125rem;
                font-weight: 600; color: {C["texto"]} !important; white-space: nowrap; }}
.ficha-neta {{ background: #F6F8FB; border-radius: 0.75rem; padding: 0.875rem 1rem; margin: 0.875rem 0; }}
.ficha-neta .cab {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline;
                    gap: 0.25rem 0.75rem; font-size: 0.8125rem; color: {C["texto_2"]}; }}
.ficha-neta .cab b {{ font-size: 1.25rem; font-weight: 600; color: {C["texto"]}; }}
.ficha-neta .marcas {{ color: {C["texto_2"]}; }}
.ficha-datos {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(12.5rem, 1fr)); gap: 0.75rem 1.5rem; margin: 0; }}
.ficha-datos dt {{ font-size: 0.75rem; color: {C["texto_2"]}; }}
.ficha-datos dd {{ margin: 0; font-size: 0.875rem; }}
/* Pestana 4 */
.equilibrios {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; }}
.equilibrio {{ background: {C["fondo"]}; border: 1px solid {C["borde"]}; border-radius: 1rem; padding: 1rem;
               display: flex; flex-direction: column; gap: 0.375rem; }}
.equilibrio span {{ display: inline-flex; align-items: center; gap: 0.375rem; font-size: 0.75rem; font-weight: 500;
                    color: {C["texto_2"]}; }}
.equilibrio b {{ font-size: 1.875rem; line-height: 1.05; font-weight: 600; letter-spacing: -0.02em; }}
.conclusion {{ background: {C["texto"]}; color: #FFFFFF; border-radius: 1rem; padding: 1.25rem;
               font-size: 1.125rem; line-height: 1.35; font-weight: 600; margin-top: 0.25rem; }}
/* Pestana 5 */
.sens-grupo {{ font-size: 0.6875rem; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase;
               color: {C["texto_2"]}; margin: 0.75rem 0 0.25rem; }}
.sens-fila {{ display: grid; grid-template-columns: 10.625rem minmax(0, 1fr); align-items: center; gap: 0.75rem;
              padding: 0.25rem 0.5rem; margin: 0 -0.5rem; border-radius: 0.5rem; font-size: 0.8125rem; }}
.sens-fila.base {{ background: {C["fondo_2"]}; font-weight: 600; }}
.sens-barras {{ display: flex; flex-direction: column; gap: 3px; }}
.sens-barras div {{ display: flex; align-items: center; gap: 0.375rem; font-size: 0.6875rem; line-height: 0.625rem;
                    font-weight: 500; }}
.sens-barras i {{ display: block; height: 0.5rem; border-radius: 2px; min-width: 2px; }}
.leyenda {{ display: flex; flex-wrap: wrap; gap: 0.375rem 1rem; font-size: 0.75rem; color: {C["texto_2"]}; }}
.leyenda span {{ display: inline-flex; align-items: center; gap: 0.375rem; }}
/* st.html le pone sangria a las listas: estas no la llevan. */
ol.limitaciones, dl.ficha-datos {{ padding-left: 0 !important; }}
.limitaciones {{ margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 0.75rem; }}
.limitaciones li {{ display: grid; grid-template-columns: 1.75rem minmax(0, 1fr); gap: 0.75rem; align-items: start;
                    font-size: 0.8125rem; line-height: 1.5; }}
.limitaciones li > span:first-child {{ width: 1.75rem; height: 1.75rem; border-radius: 0.5rem; background: {C["fondo_2"]};
                           display: flex; align-items: center; justify-content: center; font-size: 0.75rem;
                           font-weight: 600; }}
.fuentes {{ width: 100%; border-collapse: collapse; font-size: 0.8125rem; }}
.fuentes th {{ text-align: left; font-weight: 500; font-size: 0.75rem; color: {C["texto_2"]};
               padding: 0 0.75rem 0.5rem 0; border-bottom: 1px solid #E8ECF2; }}
.fuentes td {{ padding: 0.5625rem 0.75rem 0.5625rem 0; border-bottom: 1px solid #F0F2F6; }}
.fuentes td:nth-child(n+2) {{ white-space: nowrap; font-size: 0.75rem; }}
</style>
""", unsafe_allow_html=True)

def tip(texto: str) -> str:
    """Icono de ayuda con su explicacion; se abre con el mouse o con el foco del teclado."""
    return (f'<span class="tip" tabindex="0" role="img" aria-label="{html.escape(texto, quote=True)}" '
            f'data-tip="{html.escape(texto, quote=True)}">{INFO}</span>')


# --- Encabezado -------------------------------------------------------------------
lo_p, hi_p = S.PRESUPUESTO_USD
LIMITACIONES = [
    ("Precios de publicación",
     "Son precios de publicación, no de cierre. La venta y el alquiler son precios pedidos; "
     "el precio de cierre suele ser menor."),
    ("Una sola inmobiliaria, ~8% más barata",
     "Es la cartera de una sola inmobiliaria, que publica más barato que el mercado: contra "
     "IDECBA, RE/MAX publica alrededor de 8% más barato (9% en los usados). Las rentabilidades "
     "probablemente están del lado alto."),
    ("Cada rentabilidad es una banda",
     "Cada rentabilidad es una banda, no un número. El alquiler es una estimación: su banda "
     "del percentil 10 al 90 contiene al 82% de los alquileres reales."),
]
st.html(
    f'<header class="cabecera"><div><h1>¿Conviene comprar para alquilar?</h1>'
    f'<p>Tengo entre USD {num(lo_p)} y {num(hi_p)}: ¿conviene comprar para alquilar, y si compro, qué?</p></div>'
    f'<div class="contador"><span><b>{num(len(vista))}</b> <span class="gris">de {num(len(df))} '
    f'propiedades</span></span><div class="barra"><div style="width: {len(vista) / len(df) * 100:.1f}%">'
    f'</div></div><span class="pie">Cartera RE/MAX · relevada el {T.fechas_relevamiento(df)}</span></div>'
    f'</header>')
with st.container(horizontal=True, key="limitaciones"):
    for etiqueta, texto in LIMITACIONES:
        with st.popover(etiqueta, icon=":material/info:"):
            st.markdown(texto)


# --- Graficos ---------------------------------------------------------------------
ALTO = round(340 * ESCALA)
SIN_BARRA = {"displayModeBar": False}


def estilo(fig: go.Figure, margen_derecho: int = 10, alto: int = ALTO) -> go.Figure:
    fig.update_layout(height=alto, margin=dict(l=8, r=margen_derecho, t=24, b=8),
                      plot_bgcolor=C["fondo"], paper_bgcolor=C["fondo"],
                      font=dict(family=FUENTE, color=C["texto"]), showlegend=False)
    fig.update_xaxes(showgrid=False, linecolor=C["en_banda"], ticks="outside", tickcolor=C["borde"],
                     tickfont=dict(color=C["texto_2"], size=11))
    fig.update_yaxes(gridcolor="#EEF1F6", zeroline=False, tickfont=dict(color=C["texto_2"], size=11))
    return fig


def histograma(v, columna: str) -> go.Figure:
    serie = v[columna].dropna()
    x0, x1 = serie.quantile(0.005), serie.quantile(0.995)
    recortada = serie.clip(x0, x1)
    pico = np.histogram(recortada, bins=np.arange(np.floor(x0), x1 + 0.25, 0.25))[0].max()
    fig = go.Figure(go.Histogram(
        x=recortada, xbins=dict(size=0.25), marker=dict(color=C["principal"], line=dict(color=C["fondo"], width=1)),
        hovertemplate="%{x} %<br>%{y} propiedades<extra></extra>"))
    fig.add_vrect(x0=PISO, x1=TECHO, fillcolor=C["acento"], opacity=0.6, layer="below", line_width=0)
    mediana = serie.median()
    fig.add_vline(x=mediana, line_dash="dash", line_color=C["texto"], line_width=1.5,
                  annotation_text=f"<b>mediana {pct(mediana)}</b>", annotation_position="top left",
                  annotation_font_color=C["texto"], annotation_bgcolor="rgba(255,255,255,0.9)")
    fig.update_xaxes(range=[min(x0, PISO) - 0.5, max(x1, TECHO) + 0.5], ticksuffix="%")
    fig.update_yaxes(range=[0, pico * 1.15])
    return estilo(fig)


ETAPAS = ["Universo de la decisión", "Neta central sobre el techo", "P1 · pesimista sobre el techo",
          "TIR pesimista sobre el techo"]


def etapas_html(etapas) -> str:
    """Barras en escala lineal con la cifra afuera, para que se lean el 18 y el 4."""
    universo = etapas[0][1]
    # Las dos ultimas etapas son candidatas "a verificar": color de alerta.
    colores = [C["principal"], C["principal"], C["alerta"], C["alerta"]]
    filas = []
    for (largo, n), corto, color in zip(etapas, ETAPAS, colores):
        parte = n / universo * 100 if universo else 0
        cifra = pct(parte, 0 if parte in (0, 100) else 1) if universo else "–"
        minimo = "min-width: 4px; " if n else ""
        filas.append(f'<div title="{html.escape(largo)}: {num(n)} propiedades"><div class="etapa-cab">'
                     f'<span>{corto}</span><span class="cifra"><b>{num(n)}</b> · {cifra}</span></div>'
                     f'<div class="pista"><div style="{minimo}width: {parte:.2f}%; background: {color}"></div>'
                     f'</div></div>')
    return f'<div class="etapas">{"".join(filas)}</div>'


def dominio(*valores) -> tuple:
    """Eje de las escalas chicas: al menos de 3% a 9%, y siempre con la banda adentro."""
    return min(3, np.floor(min(valores))), max(9, np.ceil(max(valores)), np.ceil(TECHO) + 1)


def posicion(x: float, d: tuple) -> float:
    return float(np.clip((x - d[0]) / (d[1] - d[0]) * 100, 0, 100))


def lectura_html(k: dict) -> str:
    """La conclusion con estos filtros, con la neta mediana, su banda y la distancia al piso."""
    d = dominio(k["neta_min_mediana"], k["neta_max_mediana"], k["neta_mediana"])
    p = lambda x: posicion(x, d)
    pp = k["pp_al_piso"]
    if pp < 0:
        frase = (f'La propiedad típica rinde <em>{num(-pp, 2)} pp menos</em> que una ON en dólares: '
                 'no conviene comprar.')
    else:
        frase = f'La propiedad típica rinde <em>{num(pp, 2)} pp más</em> que el piso de la renta fija en dólares.'
    a, b = sorted((p(k["neta_mediana"]), p(PISO)))
    marcas = "".join(f'<span style="left: {p(v)}%">{v:.0f}%</span>' for v in range(int(d[0]), int(d[1]) + 1))
    return (
        f'<div class="lectura"><p class="frase">{frase}</p>'
        f'<div class="escala" style="height: 40px; margin-top: 4px">'
        f'<div style="left: 0; right: 0; top: 19px; height: 2px; background: #555B6B"></div>'
        f'<div style="top: 4px; bottom: 4px; left: {p(PISO)}%; width: {p(TECHO) - p(PISO)}%; '
        f'background: {C["acento"]}; border-radius: 3px"></div>'
        f'<div style="top: 14px; height: 12px; left: {p(k["neta_min_mediana"])}%; '
        f'width: {p(k["neta_max_mediana"]) - p(k["neta_min_mediana"])}%; background: rgba(197,213,234,0.35); '
        f'border-radius: 6px"></div>'
        f'<div style="top: 19px; height: 2px; left: {a}%; width: {b - a}%; background: {C["acento"]}"></div>'
        f'<div style="top: 12px; left: {p(k["neta_mediana"])}%; width: 16px; height: 16px; margin-left: -8px; '
        f'border-radius: 50%; background: #FFFFFF; border: 3px solid {C["texto"]}; box-sizing: border-box"></div>'
        f'</div><div class="marcas">{marcas}</div>'
        f'<div class="leyenda"><span><span class="punto" style="background: #FFFFFF"></span>Neta mediana '
        f'{pct(k["neta_mediana"])}</span><span><span style="width: 18px; height: 8px; border-radius: 4px; '
        f'background: rgba(197,213,234,0.35)"></span>Su banda {pct(k["neta_min_mediana"])}–'
        f'{pct(k["neta_max_mediana"])}</span><span><span style="width: 18px; height: 2px; '
        f'background: {C["acento"]}"></span>Distancia al piso {num(pp, 2).replace("-", "−")} pp</span></div></div>')


def kpi_html(titulo: str, ayuda: str, valor: str, sub: str, escala: str) -> str:
    sub = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (f'<div class="kpi"><div class="kpi-cab"><span>{titulo}</span>{tip(ayuda)}</div>'
            f'<div class="kpi-valor">{valor}</div>{sub}<div class="escala">{escala}</div></div>')


def escala_punto(x: float, d: tuple, banda: tuple = None) -> str:
    """Escala chica: la franja de la banda, la banda propia (si hay) y el valor."""
    p = lambda v: posicion(v, d)
    propia = (f'<div style="top: 3px; height: 8px; left: {p(banda[0])}%; width: {p(banda[1]) - p(banda[0])}%; '
              f'background: {rgba(C["principal"], 0.25)}; border-radius: 4px"></div>') if banda else ""
    return (f'<div style="left: 0; right: 0; top: 6px; height: 2px; background: {C["borde"]}"></div>'
            f'<div style="top: 0; bottom: 0; left: {p(PISO)}%; width: {p(TECHO) - p(PISO)}%; '
            f'background: {C["acento"]}; border-radius: 2px"></div>{propia}'
            f'<div style="top: 2px; left: {p(x)}%; width: 10px; height: 10px; margin-left: -5px; '
            f'border-radius: 50%; background: {C["principal"]}"></div>')


def escala_posiciones(v, columna: str) -> str:
    """Barra apilada: debajo del piso, dentro de la banda y sobre el techo."""
    pos = T.posicion_banda(v[columna]).dropna()
    partes = [(pos == clave).mean() * 100 for clave in T.POSICIONES]
    return ('<div class="apilada" style="position: absolute; left: 0; right: 0; top: 3px; height: 8px">'
            + "".join(f'<div style="width: {parte:.2f}%; background: {color}"></div>'
                      for parte, (_, color) in zip(partes, T.POSICIONES.values())) + '</div>')


ALTO_2 = round(470 * ESCALA)       # ranking y H1, lado a lado debajo del mapa
ALTO_MAPA = round(560 * ESCALA)    # el mapa va primero, con su panel al lado


def puntos_barrio(rk, elegidos: tuple) -> go.Figure:
    """Neta (con su banda) y TIR medianas por barrio; los elegidos en el filtro, resaltados."""
    resaltado = rk["barrio"].isin(elegidos) if elegidos else pd.Series(True, index=rk.index)
    fig = go.Figure()
    fig.add_vrect(x0=PISO, x1=TECHO, fillcolor=C["acento"], opacity=0.55, layer="below", line_width=0)
    for grupo, opacidad in ((~resaltado, 0.25), (resaltado, 1.0)):
        sub = rk[grupo]
        if sub.empty:
            continue
        leyenda = opacidad == 1.0
        xs, ys = [], []
        for nombre, lo, hi in zip(sub["barrio_nombre"], sub["neta_min"], sub["neta_max"]):
            xs += [lo, hi, None]
            ys += [nombre, nombre, None]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=C["principal"], width=4),
                                 opacity=opacidad * 0.3, name="Banda de la neta", showlegend=leyenda,
                                 hoverinfo="skip"))
        fig.add_trace(go.Scatter(
            x=sub["rent_neta"], y=sub["barrio_nombre"], mode="markers", opacity=opacidad,
            marker=dict(color=C["principal"], size=9, line=dict(color=C["fondo"], width=1)),
            name="Neta mediana", showlegend=leyenda,
            customdata=sub[["neta_min", "neta_max", "n_ventas"]],
            hovertemplate="%{y}: neta %{x:.2f}% (banda %{customdata[0]:.2f}% a %{customdata[1]:.2f}%)"
                          "<br>%{customdata[2]} ventas<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=sub["tir_5a"], y=sub["barrio_nombre"], mode="markers", opacity=opacidad,
            marker=dict(color=C["secundario"], size=7, symbol="diamond"), name="TIR 5 años",
            showlegend=leyenda, hovertemplate="%{y}: TIR %{x:.2f}%<extra></extra>"))
    # El orden del eje es el del ranking (por neta), no el de aparicion de las trazas.
    nombres = list(rk["barrio_nombre"])
    marcados = [f"<b>{n}</b>" if r and elegidos else n for n, r in zip(nombres, resaltado)]
    fig.update_yaxes(categoryorder="array", categoryarray=nombres, tickvals=nombres, ticktext=marcados,
                     tickfont=dict(size=11, color=C["texto"]), showgrid=False)
    fig.update_xaxes(showgrid=True, gridcolor="#EEF1F6", ticksuffix="%")
    estilo(fig, alto=ALTO_2)
    fig.update_layout(showlegend=True, separators=",.", margin=dict(l=8, r=10, t=8, b=8),
                      legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom", font=dict(size=12)))
    return fig


def mapa(v, columna: str, metrica: str, seleccion=None) -> go.Figure:
    con = v.dropna(subset=["latitud", "longitud"])
    pos = T.posicion_banda(con[columna])
    fig = go.Figure()
    # Primero la mayoria (debajo del piso), arriba las que pasan: si no, las tapa.
    for clave, (nombre, color) in T.POSICIONES.items():
        sub = con[pos == clave]
        fig.add_trace(go.Scattermap(
            lat=sub["latitud"], lon=sub["longitud"], mode="markers", name=nombre,
            marker=dict(size=6, color=color, opacity=0.8),
            customdata=np.column_stack([sub["barrio_nombre"], sub["venta_usd"], sub[columna],
                                        sub["neta_min_pct"], sub["neta_max_pct"]]),
            hovertemplate="%{customdata[0]} · USD %{customdata[1]:,.0f}<br>"
                          f"{metrica} " "%{customdata[2]:.2f}% · banda de la neta "
                          "%{customdata[3]:.2f}% a %{customdata[4]:.2f}%<extra></extra>"))
    elegida = con[con["id_aviso"] == seleccion]
    if not elegida.empty:
        # Scattermap no tiene borde de marcador: un circulo blanco 4 px mas grande hace de borde
        # de 2 px. Va al final, asi queda encima; el doble de grande que el resto (6 px).
        for tam, color in ((16, C["fondo"]), (12, C["seleccion"])):
            fig.add_trace(go.Scattermap(lat=elegida["latitud"], lon=elegida["longitud"], mode="markers",
                                        marker=dict(size=tam, color=color), hoverinfo="skip"))
    # La leyenda, con las cantidades, va en el panel de al lado.
    fig.update_layout(height=ALTO_MAPA, margin=dict(l=0, r=0, t=0, b=0), separators=",.", showlegend=False,
                      # Con un mapa mas bajo, menos zoom: entra la misma Ciudad.
                      map=dict(style="carto-positron", center=dict(lat=-34.603, lon=-58.445),
                               zoom=10.9 + np.log2(ESCALA)),
                      paper_bgcolor=C["fondo"], font=dict(family=FUENTE))
    return fig


def panel_mapa(v, columna: str, seleccion=None) -> str:
    """Leyenda del mapa con cantidades, los barrios con mas propiedades sobre el techo y las faltantes."""
    pos = T.posicion_banda(v[columna]).dropna()
    total = len(pos)
    filas = []
    for clave, (nombre, color) in T.POSICIONES.items():
        n = int((pos == clave).sum())
        filas.append(f'<div class="fila-leyenda"><span><span class="punto" style="background: {color}"></span>'
                     f'{html.escape(nombre)}</span><span><b>{num(n)}</b> · {pct(n / total * 100, 1)}</span></div>')
    if seleccion is not None and (v["id_aviso"] == seleccion).any():
        filas.append(f'<div class="fila-leyenda"><span><span class="punto" style="background: {C["seleccion"]}">'
                     '</span>Propiedad elegida</span></div>')
    apilada = "".join(f'<div style="width: {(pos == clave).mean() * 100:.2f}%; background: {color}"></div>'
                      for clave, (_, color) in T.POSICIONES.items())
    sobre = v.loc[pos.index[pos == "sobre"], "barrio_nombre"].value_counts().head(6)
    barrios = "".join(f'<div class="fila-barrio"><span>{html.escape(b)}</span><div class="pista">'
                      f'<div style="width: {n / sobre.iloc[0] * 100:.1f}%; background: {C["sobre_techo"]}"></div>'
                      f'</div><b>{n}</b></div>' for b, n in sobre.items())
    faltan = T.sin_coordenadas(v)
    nota = (f"{faltan} {'aviso' if faltan == 1 else 'avisos'} sin coordenadas no "
            f"{'aparece' if faltan == 1 else 'aparecen'} en el mapa." if faltan
            else "Todas las propiedades tienen coordenadas.")
    bloque_sobre = (f'<hr><p class="rotulo">Dónde están las {num(int((pos == "sobre").sum()))} '
                    f'sobre el techo</p>{barrios}') if len(sobre) else ""
    return (f'<div class="panel"><p class="rotulo">Posición respecto de la banda</p>'
            f'<div class="apilada">{apilada}</div>{"".join(filas)}{bloque_sobre}<hr>'
            f'<span class="nota">{nota}</span></div>')


def dispersion_h1(h: dict) -> go.Figure:
    b = h["barrios"]
    fig = go.Figure()
    fig.add_hrect(y0=PISO, y1=TECHO, fillcolor=C["acento"], opacity=0.55, layer="below", line_width=0)
    x = np.array([b["m2"].min(), b["m2"].max()])
    fig.add_trace(go.Scatter(x=x, y=h["ordenada"] + h["pendiente_m2"] * x, mode="lines",
                             line=dict(color=C["contexto"], dash="dash", width=1.5), hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=b["m2"], y=b["bruta"], mode="markers",
        marker=dict(color=C["principal"], size=10, line=dict(color=C["fondo"], width=1.5)),
        customdata=b[["barrio_nombre", "n"]],
        hovertemplate="%{customdata[0]}: USD %{x:,.0f}/m² · bruta %{y:.2f}%<br>%{customdata[1]} ventas"
                      "<extra></extra>"))
    fig.update_xaxes(title=dict(text="USD por m² del barrio", font=dict(size=12, color=C["texto_2"])))
    fig.update_yaxes(title=dict(text="Bruta (% anual)", font=dict(size=12, color=C["texto_2"])),
                     ticksuffix="%")
    fig.update_layout(separators=",.")
    return estilo(fig, alto=ALTO_2 - round(70 * ESCALA))


AVISO_VIEJO = (f"Aviso de RE/MAX relevado el {T.fechas_relevamiento(df)}. Si ya se vendió o "
               "se dio de baja, el link abre la portada de RE/MAX.")
ANCHO_BARRA_P2 = 0.85          # en unidades del eje: 1 - bargap
ALTO_3 = round(540 * ESCALA)       # rangos de la frontera P2: 140 barras en una pantalla


def rangos_p2(fr, seleccion) -> go.Figure:
    """Una barra de neta_min a neta_max por propiedad, ordenadas por ancho de banda."""
    elegida = (fr["id_aviso"] == seleccion).to_numpy()
    hay_elegida = bool(elegida.any())
    # Con una elegida, el resto se atenua sin perder su color.
    alfa = 0.35 if hay_elegida else 1.0
    colores = np.where(fr["p1_comprar"], rgba(C["alerta"], alfa), rgba(C["principal"], alfa))
    fig = go.Figure()
    # Con 140 barras encima, la franja sola no se ve: se marcan tambien sus bordes por arriba.
    fig.add_vrect(x0=PISO, x1=TECHO, fillcolor=C["acento"], opacity=0.55, layer="below", line_width=0)
    for x in (PISO, TECHO):
        fig.add_vline(x=x, line_color=C["alerta"], line_width=1, line_dash="dot", layer="above")
    # Una sola traza clickeable: el indice del punto es la fila de fr. La leyenda va aparte.
    fig.add_trace(go.Bar(
        y=np.arange(len(fr)), x=fr["ancho"], base=fr["neta_min_pct"], orientation="h",
        marker=dict(color=colores),
        customdata=np.column_stack([fr["barrio_nombre"], fr["venta_usd"], fr["sup_total_m2"],
                                    fr["neta_min_pct"], fr["neta_max_pct"], fr["ancho"]]),
        hovertemplate="%{customdata[0]} · USD %{customdata[1]:,.0f} · %{customdata[2]:.0f} m²<br>"
                      "neta %{customdata[3]:.2f}% a %{customdata[4]:.2f}% "
                      "(ancho %{customdata[5]:.2f} pp)<extra></extra>",
        showlegend=False))
    if hay_elegida:
        # Traza aparte, encima y mas gruesa (sin borde: en barras finas tapa el relleno).
        i = int(np.flatnonzero(elegida)[0])
        fila = fr.iloc[i]
        fig.add_trace(go.Bar(y=[i], x=[fila["ancho"]], base=[fila["neta_min_pct"]], orientation="h",
                             width=[ANCHO_BARRA_P2 * 2.5], marker_color=C["seleccion"], showlegend=False,
                             hovertemplate=f"{html.escape(fila['barrio_nombre'])} (elegida)<extra></extra>"))
        fig.add_annotation(x=fila["neta_max_pct"], y=i, text="<b>Elegida</b>", xanchor="left", xshift=4,
                           showarrow=False, font=dict(color=C["texto"], size=12),
                           bgcolor="rgba(255,255,255,0.9)")
    leyenda = [("A verificar (P1)", C["alerta"]), ("Resto de la frontera", C["principal"])]
    if hay_elegida:
        leyenda.append(("Propiedad elegida", C["seleccion"]))
    for nombre, color in leyenda:
        fig.add_trace(go.Bar(x=[None], y=[None], orientation="h", marker_color=color, name=nombre,
                             hoverinfo="skip"))
    estilo(fig, alto=ALTO_3)
    # overlay: con el modo por defecto (group) la traza de la elegida parte cada fila en dos,
    # las barras se corren y los clics caen en el hueco.
    fig.update_layout(bargap=1 - ANCHO_BARRA_P2, barmode="overlay", separators=",.", showlegend=True,
                      clickmode="event+select",
                      margin=dict(l=8, r=10, t=8, b=8),
                      legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom", font=dict(size=12)))
    fig.update_yaxes(autorange="reversed", showticklabels=False, showgrid=False,
                     title=dict(text="↑ banda más angosta · más ancha ↓", font=dict(size=12, color=C["texto_2"])))
    fig.update_xaxes(title=dict(text="Neta: de la pesimista a la optimista", font=dict(size=12, color=C["texto_2"])),
                     showgrid=True, gridcolor="#EEF1F6", ticksuffix="%")
    return fig


def ficha_html(f) -> str:
    """La ficha de la propiedad elegida: todo lo que hace falta para ir a verificarla."""
    e = html.escape
    d = (min(4, np.floor(f["neta_min_pct"]) - 1), max(20, np.ceil(f["neta_max_pct"]) + 1))
    p = lambda x: posicion(x, d)
    ambientes = f" · {num(f['ambientes'])} ambientes" if pd.notna(f["ambientes"]) else ""
    datos = [
        ("Precio", f"USD {num(f['venta_usd'])} · {num(f['sup_total_m2'])} m² · USD {num(f['venta_m2_usd'])}/m²"),
        ("m² contra su celda", f"{num((f['m2_relativo_celda'] - 1) * 100)}% contra el mediano de su barrio y tamaño"),
        ("Alquiler estimado", f"USD {num(f['alquiler_est_usd_mes'])}/mes (p10–p90: "
                              f"{num(f['alquiler_p10_usd_mes'])} a {num(f['alquiler_p90_usd_mes'])})"),
        ("TIR a 5 años", f"{pct(f['tir_5a_pct'])} (pesimista {pct(f['tir_5a_min_pct'])})"),
        ("Costos de entrada", f"{pct(f['costos_entrada_pct'])} del precio"),
        ("Transporte", f"{e(str(f['modo_cercano']).capitalize())} a {num(f['dist_transporte_m'])} m"),
        ("Publicación típica (Ciudad)", f"{num(f['dias_publicacion_ambientes'])} días"),
    ]
    cuerpo = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in datos)
    return (
        f'<div class="ficha-cab"><div><p class="ficha-titulo">{e(str(f["titulo"]))}</p>'
        f'<span class="nota">{e(f["barrio_nombre"])}{ambientes}</span></div>'
        f'<a class="ficha-boton" href="{e(str(f["url"]), quote=True)}" target="_blank" rel="noopener" '
        f'title="{e(AVISO_VIEJO, quote=True)}">Ver aviso ↗</a></div>'
        f'<div class="ficha-neta"><div class="cab"><span>Neta <b>{pct(f["rent_neta_pct"])}</b></span>'
        f'<span>banda {pct(f["neta_min_pct"])} a {pct(f["neta_max_pct"])}</span></div>'
        f'<div class="escala" style="height: 16px; margin-top: 8px">'
        f'<div style="left: 0; right: 0; top: 7px; height: 2px; background: #DDE3EC"></div>'
        f'<div style="top: 0; bottom: 0; left: {p(PISO)}%; width: {p(TECHO) - p(PISO)}%; '
        f'background: {C["acento"]}; border-radius: 2px"></div>'
        f'<div style="top: 4px; height: 8px; left: {p(f["neta_min_pct"])}%; '
        f'width: {p(f["neta_max_pct"]) - p(f["neta_min_pct"])}%; background: {rgba(C["seleccion"], 0.35)}; '
        f'border-radius: 4px"></div>'
        f'<div style="top: 3px; left: {p(f["rent_neta_pct"])}%; width: 10px; height: 10px; margin-left: -5px; '
        f'border-radius: 50%; background: {C["seleccion"]}; border: 1.5px solid #FFFFFF; box-sizing: border-box">'
        f'</div></div><div class="marcas" style="margin-top: 6px"><span style="left: 0; transform: none">'
        f'{d[0]:.0f}%</span><span style="left: auto; right: 0; transform: none">{d[1]:.0f}%</span></div></div>'
        f'<dl class="ficha-datos">{cuerpo}</dl>')


ALTO_4 = round(500 * ESCALA)


@st.cache_data
def cargar_p3():
    return T.cargar_p3()


@st.cache_data
def ocupacion_airbnb():
    return T.ocupacion_airbnb()


def lineas_p3(sub, ocupacion_ia: float) -> go.Figure:
    """Celdas (de 47) donde gana el temporal segun la ocupacion, una linea por gestion."""
    celdas = int(sub["celdas"].iloc[0])
    # Etiquetas directas donde las lineas estan mas separadas (al final se juntan en 47). La
    # de arriba va a la izquierda de su tramo de subida, a media altura (arriba estan los
    # rotulos de las referencias); la de abajo, debajo y a la derecha de su punto.
    piv = sub.pivot(index="ocupacion_sostenible_pct", columns="gestion", values="gana_temporal")
    x_etiqueta = (piv.max(axis=1) - piv.min(axis=1)).idxmax()
    arriba = piv.loc[x_etiqueta].idxmax()
    fig = go.Figure()
    for gestion, (nombre, color) in T.GESTIONES.items():
        g = sub[sub["gestion"] == gestion]
        fig.add_trace(go.Scatter(
            x=g["ocupacion_sostenible_pct"], y=g["gana_temporal"], mode="lines+markers", name=nombre,
            line=dict(color=color, width=2.5), marker=dict(color=color, size=8, line=dict(color=C["fondo"], width=1.5)),
            hovertemplate=f"{nombre}: con %{{x:.0f}}% de ocupación gana en %{{y}} de {celdas} celdas"
                          "<extra></extra>"))
        if gestion == arriba:
            medio = (g["gana_temporal"] - celdas * 0.45).abs().idxmin()
            fig.add_annotation(x=g.loc[medio, "ocupacion_sostenible_pct"], y=g.loc[medio, "gana_temporal"],
                               text=f"<b>{nombre}</b>", showarrow=False, xanchor="right", xshift=-8,
                               font=dict(color=color, size=13))
        else:
            fig.add_annotation(x=x_etiqueta, y=piv.loc[x_etiqueta, gestion], text=f"<b>{nombre}</b>",
                               showarrow=False, xanchor="left", xshift=8, yanchor="top", yshift=-4,
                               font=dict(color=color, size=13))
    for x, texto in ((ocupacion_ia, f"Inside Airbnb<br>{pct(ocupacion_ia, 1)}"),
                     (S.OCUPACION_REF_PCT, f"Prensa<br>{pct(S.OCUPACION_REF_PCT, 0)}")):
        fig.add_vline(x=x, line_dash="dash", line_color=C["contexto"], line_width=1.5)
        fig.add_annotation(x=x, y=1, yref="paper", text=texto, showarrow=False, xanchor="left", xshift=4,
                           yanchor="top", align="left", font=dict(color=C["texto"], size=11))
    estilo(fig, margen_derecho=20, alto=ALTO_4)
    fig.update_xaxes(title=dict(text="Ocupación sostenible del temporal (% del año)",
                                font=dict(size=12, color=C["texto_2"])), ticksuffix="%",
                     range=[min(ocupacion_ia, sub["ocupacion_sostenible_pct"].min()) - 4,
                            sub["ocupacion_sostenible_pct"].max() + 3])
    fig.update_yaxes(title=dict(text=f"Celdas donde gana el temporal (de {celdas})",
                                font=dict(size=12, color=C["texto_2"])), range=[-1, celdas + 2])
    fig.update_layout(separators=",.")
    return fig


# README, "Limitaciones", y el informe (causalidad). Las tres primeras son las del encabezado.
LIMITACIONES_COMPLETAS = [
    ("Precios de publicación, no de cierre", "del lado de la venta y del alquiler."),
    ("Una sola inmobiliaria", "RE/MAX publica alrededor de 8% más barato que el mercado y está sesgada en "
                              "cobertura geográfica: las rentabilidades probablemente están del lado alto."),
    ("Cada rentabilidad es una banda", "el alquiler es estimado; su banda p10–p90 contiene al 82% de los "
                                       "alquileres reales."),
    ("Casas y PH fuera de las recomendaciones", "hay muy pocos alquileres observados."),
    ("Sin apreciación, costos de salida ni riesgo legal", "la TIR supone reventa al mismo precio en "
                                                          "dólares; el riesgo legal no tiene fuente."),
    ("Liquidez de toda la Ciudad", "el tiempo de publicación de IDECBA es por ambientes, no por barrio ni "
                                   "por propiedad."),
    ("No es causalidad", "comparar dentro del estrato controla por zona, tamaño y tipología, no por todo."),
]


@st.cache_data
def cargar_sensibilidad():
    return T.cargar_sensibilidad()


@st.cache_data
def cargar_fuentes():
    return T.fuentes()


def sensibilidad_html(s) -> str:
    """Cuantas pasan P1 y P1 con entrada en cada escenario, agrupados por supuesto; los iguales a la base, marcados."""
    tope = max(s["n_p1"].max(), s["n_p1_con_entrada"].max(), 1)
    partes = []
    for parametro, g in s.groupby("parametro", sort=False):
        if len(g) > 1:
            partes.append(f'<p class="sens-grupo">{html.escape(str(parametro))}</p>')
        for r in g.itertuples():
            barras = "".join(f'<div><i style="width: {n / tope * 92:.1f}%; background: {color}"></i>{n}</div>'
                             for n, color in ((r.n_p1, C["alerta"]), (r.n_p1_con_entrada, C["principal"])))
            partes.append(f'<div class="sens-fila{" base" if r.es_base else ""}" '
                          f'title="{html.escape(r.escenario)}: {r.n_p1} pasan P1, {r.n_p1_con_entrada} con costos '
                          f'de entrada"><span>{html.escape(r.escenario)}</span><div class="sens-barras">{barras}</div>'
                          f'</div>')
    return "".join(partes)


# --- Pestanas ---------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs(["¿Conviene comprar?", "¿Dónde?", "¿Qué comprar?",
                                        "¿Tradicional o temporal?", "Supuestos y alcance"])
NO_FILTRA = dict(icon=":material/lock:", color="gray")

with tab1:
    k = T.kpis(vista)
    if k["n"] == 0:
        st.info("Ninguna propiedad cumple estos filtros. Probá ampliarlos o tocá **Restablecer filtros**.")
    else:
        if k["n"] < MIN_CONFIABLE:
            st.warning(f"Quedan {k['n']} propiedades: con menos de {MIN_CONFIABLE} la mediana es "
                       "poco confiable.")
        sin_soporte = filtros.tipo in T.SIN_SOPORTE

        c0, c1, c2, c3 = st.columns([2, 1, 1, 1])
        d = dominio(k["neta_min_mediana"], k["neta_max_mediana"], k["tir_mediana"])
        c0.html(lectura_html(k))
        # La banda va en la tarjeta: GUIA_TABLERO.md pide no mostrar nunca la neta sola.
        c1.html(kpi_html("Neta mediana", "Rentabilidad neta anual mediana. La banda es la mediana de la neta "
                         "con el alquiler en sus percentiles 10 y 90: cada rentabilidad es una banda, no un número.",
                         pct(k["neta_mediana"]), f"banda {pct(k['neta_min_mediana'])} a {pct(k['neta_max_mediana'])}",
                         escala_punto(k["neta_mediana"], d, (k["neta_min_mediana"], k["neta_max_mediana"]))))
        c2.html(kpi_html("TIR a 5 años mediana", "Tasa interna de retorno a 5 años, con los costos de entrada de "
                         "la compra y reventa al mismo precio en dólares.", pct(k["tir_mediana"]), "",
                         escala_punto(k["tir_mediana"], d)))
        c3.html(kpi_html("Neta sobre el piso", f"Propiedades con neta de {pct(PISO)} o más. La barra las separa: "
                         "debajo del piso (azul), dentro de la banda (gris) y sobre el techo (ocre).",
                         pct(k["pct_sobre_piso"], 1), "", escala_posiciones(vista, "rent_neta_pct")))

        g1, g2 = st.columns([3, 2])
        columna, etiqueta = METRICAS[ss["metrica"]]
        with g1, st.container(border=True, key="tarjeta_histograma"):
            st.markdown(f"**Distribución de la {ss['metrica'].lower()}**",
                        help=f"Cada barra cuenta propiedades por su {etiqueta.split(' (')[0].lower()} "
                             "central; la de cada una es una banda, no un número. La franja amarilla "
                             f"es la banda de retorno mínimo, {pct(PISO)} a {pct(TECHO)}: lo que paga "
                             "la renta fija en dólares (ON de YPF 2031 y Pampa 2037).")
            st.plotly_chart(histograma(vista, columna), width="stretch", config=SIN_BARRA)
        with g2, st.container(border=True, key="tarjeta_etapas"):
            if sin_soporte:
                st.warning(f"El modelo casi no tiene alquileres observados de {T.TIPOS[filtros.tipo]}: "
                           "sus rentabilidades son extrapolaciones y no entran en las recomendaciones.")
            else:
                st.markdown("**¿Cuántas pasan cada vara?**",
                            help="Solo departamentos dentro del presupuesto y del soporte del modelo. "
                                 "Universo → neta central sobre el techo de la banda → neta pesimista "
                                 "sobre el techo (P1) → TIR pesimista, con costos de entrada, sobre "
                                 "el techo. El porcentaje es sobre el universo.")
                st.html(etapas_html(T.embudo(vista)) +
                        f'<div class="aviso">{ALERTA}<span>Las que pasan P1 no son una recomendación: '
                        'hay que verificar por qué son baratas.</span></div>')

with tab2:
    # El mapa primero, con su panel al lado; debajo, ranking y H1 lado a lado. Esta pestana
    # tiene scroll a proposito (DISENO_TABLERO.md, seccion 6).
    with st.container(border=True, key="tarjeta_mapa"):
        columna, etiqueta = METRICAS[ss["metrica"]]
        st.markdown(f"**{ss['metrica']} de cada propiedad frente a la banda**",
                    help=f"Cada punto es una propiedad, coloreada según su {ss['metrica'].lower()} "
                         f"central: debajo del piso ({pct(PISO)}), dentro de la banda o sobre el techo "
                         f"({pct(TECHO)}). Al pasar el mouse se ve la banda de su neta.")
        if vista.empty:
            st.info("Ninguna propiedad cumple estos filtros.")
        else:
            m, panel = st.columns([3, 1.25], gap="large")
            m.plotly_chart(mapa(vista, columna, ss["metrica"], ss["seleccion"]), width="stretch",
                           config=SIN_BARRA)
            panel.html(panel_mapa(vista, columna, ss["seleccion"]))
    a, c = st.columns(2)
    with a, st.container(border=True, key="tarjeta_barrios"):
        st.markdown("**Neta y TIR por barrio**",
                    help="Barrios con 30 ventas o más (`ranking_barrios.csv`), ordenados por neta "
                         "mediana. La línea fina es la banda mediana de la neta de cada barrio. Los "
                         "barrios elegidos en el filtro se resaltan; el resto queda atenuado.")
        st.badge("No responde a los filtros", **NO_FILTRA)
        st.plotly_chart(puntos_barrio(cargar_ranking(), filtros.barrios), width="stretch", config=SIN_BARRA)
    with c, st.container(border=True, key="tarjeta_h1"):
        st.markdown("**¿El m² caro rinde menos? (H1)**",
                    help="Un punto por barrio con 30 ventas o más con estos filtros: mediana del precio "
                         "del m² contra mediana de la rentabilidad bruta. La línea es la pendiente de "
                         "Theil-Sen. La bruta todavía no descuenta vacancia ni gastos; la franja es la "
                         "banda de retorno mínimo, que se compara con la neta.")
        hh = T.h1(vista)
        if np.isnan(hh["pendiente"]):
            st.info("Con estos filtros quedan menos de 3 barrios con 30 ventas o más: "
                    "no hay pendiente que estimar.")
        else:
            st.html(f'<div class="dato"><span class="dato-valor">{num(hh["pendiente"], 2).replace("-", "−")} pp'
                    f'</span><span class="dato-sub">de rentabilidad bruta por cada USD 500/m² · IC 95% '
                    f'{num(hh["ic"][0], 2).replace("-", "−")} a {num(hh["ic"][1], 2).replace("-", "−")}</span></div>')
            st.plotly_chart(dispersion_h1(hh), width="stretch", config=SIN_BARRA)

with tab3:
    universo = vista[vista["universo_decision"]]
    if filtros.tipo in T.SIN_SOPORTE:
        st.warning(f"El modelo casi no tiene alquileres observados de {T.TIPOS[filtros.tipo]}: "
                   "no entran en P1 ni en P2.")
    elif universo.empty:
        st.info("Ninguna propiedad del universo de la decisión cumple estos filtros.")
    else:
        p1 = T.p1_tabla(vista)
        fr = T.frontera_p2(vista)
        ss["_ids_p1"], ss["_ids_p2"] = list(p1["id_aviso"]), list(fr["id_aviso"])
        izq, der = st.columns([9, 12])
        with izq, st.container(border=True, key="tarjeta_p2"):
            st.markdown(f"**Frontera P2: {num(len(fr))} que nadie supera con claridad**",
                        help="Cada barra va de la neta pesimista a la optimista de una propiedad. Están "
                             "ordenadas por ancho de banda, nunca por rentabilidad: la de arriba es la "
                             "estimación más precisa, no la mejor. Con filtros se muestra la parte de la "
                             "frontera que los cumple. Clic en una barra para ver su ficha.")
            if fr.empty:
                st.info("Ninguna propiedad de la frontera cumple estos filtros.")
            else:
                st.caption("Entre estas propiedades ninguna le gana con claridad a otra.")
                st.plotly_chart(rangos_p2(fr, ss["seleccion"]), width="stretch", config=SIN_BARRA,
                                key=clave("grafico_p2"), on_select=elegir_de_p2, selection_mode="points")
        with der:
            with st.container(border=True, key="tarjeta_p1"):
                st.markdown(f"**A verificar (P1) · {num(len(p1))}**",
                            help=f"Departamentos del universo cuya neta pesimista supera el techo de la "
                                 f"banda ({pct(TECHO)}). No es una recomendación de compra. Clic en una "
                                 "fila para ver su ficha.")
                if p1.empty:
                    st.info("Ninguna propiedad pasa P1 con estos filtros.")
                else:
                    st.html(f'<div class="aviso" style="margin: 0 0 4px">{ALERTA}<span><b>Cuestan '
                            f'~{T.descuento_p1(p1)}% menos por m² que su celda:</b> verificar por qué antes de '
                            'decidir.</span></div>')
                    tabla = pd.DataFrame({
                        "Barrio": p1["barrio_nombre"],
                        "USD": p1["venta_usd"],
                        "m²": p1["sup_total_m2"],
                        "Neta pes.": p1["neta_min_pct"],
                        "vs. celda": (p1["m2_relativo_celda"] - 1) * 100,
                        "Con entrada": p1["p1_comprar_con_entrada"],
                        "Aviso": p1["url"],
                    })
                    # Los valores quedan numericos para que la tabla ordene por numero; el Styler
                    # solo cambia lo que se ve (formato argentino, "pasa" / "—").
                    vista_tabla = tabla.style.format({
                        "USD": num, "m²": num, "Neta pes.": pct, "vs. celda": lambda x: f"{num(x)}%",
                        "Con entrada": lambda pasa: "pasa" if pasa else "—"})
                    st.dataframe(vista_tabla, hide_index=True, width="stretch", height=250, key=clave("tabla_p1"),
                                 on_select=elegir_de_p1, selection_mode="single-row",
                                 column_config={
                                     # Anchos en px: con la ficha debajo, la tabla no puede scrollear en x.
                                     "Barrio": st.column_config.TextColumn(width=115),
                                     "USD": st.column_config.NumberColumn(width=68),
                                     "m²": st.column_config.NumberColumn(width=40),
                                     "Neta pes.": st.column_config.NumberColumn(width=66, help="Neta pesimista: con el "
                                                                                "alquiler en su percentil 10."),
                                     "vs. celda": st.column_config.NumberColumn(width=62,
                                         help="Precio del m² contra el mediano de su barrio y tramo de "
                                              "superficie. Por debajo de -30%, verificar por qué es barata."),
                                     "Con entrada": st.column_config.TextColumn(width=90,
                                         help="También pasa con los costos de entrada: TIR pesimista a 5 años "
                                              "sobre el techo de la banda."),
                                     "Aviso": st.column_config.LinkColumn(display_text="ver ↗", width=46,
                                                                         help=AVISO_VIEJO)})
            with st.container(border=True, key="tarjeta_ficha"):
                elegida = T.fila(universo, ss["seleccion"])
                if elegida is None:
                    st.markdown("**Ficha de la propiedad**",
                                help="La publicación típica es la de toda la Ciudad para esa cantidad de "
                                     "ambientes (IDECBA): no distingue barrio ni propiedad. " + AVISO_VIEJO)
                    st.caption("Elegí una fila de P1 o una barra de la frontera P2.")
                else:
                    st.html(ficha_html(elegida))

with tab4:
    p3 = cargar_p3()
    opciones_vac = T.vacancias(p3)
    st.session_state.setdefault("vacancia_p3", S.VACANCIA_PCT)
    izq, der = st.columns([3, 1.2])
    with der:
        with st.container(border=True, key="tarjeta_vacancia"):
            st.pills(
                "Vacancia del alquiler tradicional", opciones_vac, key="vacancia_p3", required=True,
                format_func=lambda v: f"{pct(v, 2 if v % 1 else 0)}" + (" (base)" if v == S.VACANCIA_PCT else ""),
                help="Meses sin inquilino por año en el alquiler tradicional. La base sale de "
                     "supuestos.py: un mes vacío cada contrato de dos años. Más vacancia le resta al "
                     "tradicional y acerca al temporal.")
        sub = T.p3_vacancia(p3, ss["vacancia_p3"])
        eq = T.equilibrio(sub)
        st.html('<div class="equilibrios">' + "".join(
            f'<div class="equilibrio" title="Ocupación mediana con la que el temporal empata al tradicional, '
            f'con gestión {nombre.lower()}. Por debajo, conviene el tradicional."><span><span class="punto" '
            f'style="background: {color}"></span>Equilibrio · {nombre.lower()}</span><b>{pct(eq[gestion], 1)}</b>'
            '</div>' for gestion, (nombre, color) in T.GESTIONES.items()) + '</div>'
            '<div class="conclusion">Conviene el tradicional, salvo autogestión con evidencia de más de la mitad '
            'del año ocupado.</div>')
    with izq, st.container(border=True, key="tarjeta_p3"):
        st.markdown("**¿En cuántas celdas gana el temporal?**",
                    help="Cada celda es un barrio y una cantidad de dormitorios con datos de los dos "
                         "mercados. Para cada ocupación sostenible del temporal se cuentan las celdas "
                         "donde su neta supera a la del tradicional. Inside Airbnb estima la ocupación "
                         "desde las reseñas; la prensa (La Nación, 29-05-2025) informa 53% para CABA.")
        st.badge("No responde a los filtros", **NO_FILTRA)
        st.plotly_chart(lineas_p3(sub, ocupacion_airbnb()), width="stretch", config=SIN_BARRA)

with tab5:
    izq, der = st.columns([1.15, 1])
    with izq, st.container(border=True, key="tarjeta_sensibilidad"):
        st.markdown("**¿Cuánto cambia P1 con cada supuesto?**",
                    help="Cada fila cambia un supuesto respecto de la base, más los dos extremos que los "
                         "combinan. Las filas con fondo son iguales a la base. P1 con costos de entrada "
                         "exige que también la TIR pesimista a 5 años supere el techo de la banda.")
        st.badge("No responde a los filtros", **NO_FILTRA)
        s = cargar_sensibilidad()
        sin_extremos = s[~s["parametro"].str.startswith("extremo")]
        base = int(s.loc[s["parametro"] == "base", "n_p1"].iloc[0])
        st.html(f'<div class="dato"><span class="dato-valor">{sin_extremos["n_p1"].min()} a '
                f'{sin_extremos["n_p1"].max()}</span><span class="dato-sub">pasan P1 según el supuesto '
                f'(base: {base}), sin contar los extremos</span></div>'
                f'<div class="leyenda"><span><span class="punto" style="border-radius: 2px; background: '
                f'{C["alerta"]}"></span>Pasan P1 (neta pesimista)</span><span><span class="punto" '
                f'style="border-radius: 2px; background: {C["principal"]}"></span>P1 con costos de entrada '
                f'(TIR pesimista)</span><span><span class="punto" style="border-radius: 2px; background: '
                f'{C["fondo_2"]}"></span>Igual a la base</span></div>' + sensibilidad_html(s))
    with der:
        with st.container(border=True, key="tarjeta_limitaciones"):
            st.markdown("**Qué no se puede afirmar**")
            st.html('<ol class="limitaciones">' + "".join(
                f"<li><span>{i}</span><span><b>{html.escape(t)}</b> · {html.escape(d)}</span></li>"
                for i, (t, d) in enumerate(LIMITACIONES_COMPLETAS, start=1)) + "</ol>")
        with st.container(border=True, key="tarjeta_fuentes"):
            st.markdown("**Fuentes y fecha de los datos**",
                        help="Período que cubre cada fuente y fecha de descarga, leídos de sus tablas en "
                             "data/external/.")
            fu = cargar_fuentes()
            filas = [("RE/MAX: avisos", T.fechas_relevamiento(df), T.fechas_relevamiento(df))] + [
                (r.fuente, r.periodo or "—", r.descarga) for r in fu.itertuples()]
            st.html('<table class="fuentes"><tr><th>Fuente</th><th>Período</th><th>Descarga</th></tr>'
                    + "".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td>"
                              f"<td>{html.escape(c)}</td></tr>" for a, b, c in filas)
                    + "</table>")
            st.caption("Detalle de cada fuente en informe/FUENTES_EXTERNAS.md.")
