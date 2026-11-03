#!/usr/bin/env python
"""
datos.py — Carga, filtros y medidas de resumen del tablero.

app.py solo arma la interfaz; todo lo que se puede testear vive aca. Los KPIs
no se recalculan: se leen las columnas que materializaron kpis.py y
decision.py. Las cifras de la banda y del presupuesto salen de supuestos.py y
los nombres de barrio de eda.nombre_barrio(), nunca escritos a mano.

LOS UMBRALES, COMO EN EL PIPELINE
---------------------------------
  % sobre el piso   neta >= piso de la banda (notebook 02, 19,4% sin filtros)
  embudo            neta central > techo, luego P1 y P1 con entrada tal como
                    los guarda decision.py (que compara con > umbral)
  posicion          debajo: < piso; en banda: piso a techo inclusive; sobre: > techo
  H1                como validacion.resumen_hipotesis: medianas por barrio con
                    S.MIN_VENTAS_BARRIO ventas o mas, pendiente de Theil-Sen x 500
"""

import os
import sys
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from scipy import stats

# Repositorio solo del tablero: data/ y src/ estan junto a este archivo. En el repositorio
# del TP, datos.py esta en Entrega 3/tablero/ y la raiz es la carpeta de arriba.
RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(RAIZ, "src"))

import eda
import supuestos as S

DATASET = os.path.join(RAIZ, "data", "processed", "dataset_analitico.csv")
RANKING = os.path.join(RAIZ, "data", "processed", "ranking_barrios.csv")

# Las de GUIA_TABLERO.md ("Columnas para el tablero"), mas las del filtro de
# carga y la fecha del relevamiento para el encabezado.
COLUMNAS = [
    "id_aviso", "url", "titulo",
    "barrio", "comuna", "tipo_familia", "superficie_rango", "ambientes", "dormitorios",
    "antiguedad_rango", "venta_usd", "en_presupuesto",
    "latitud", "longitud",
    "venta_m2_usd", "sup_total_m2", "expensas_usd",
    "alquiler_est_usd_mes", "alquiler_p10_usd_mes", "alquiler_p90_usd_mes",
    "rent_bruta_pct", "rent_neta_pct", "meses_repago", "rent_bruta_min", "rent_bruta_max", "tir_5a_pct",
    "costos_entrada_pct", "abl_pct", "a_reciclar", "refaccion_usd",
    "universo_decision", "en_soporte_modelo", "neta_min_pct", "neta_max_pct", "tir_5a_min_pct",
    "p1_comprar", "p1_comprar_con_entrada", "p2_no_dominada", "m2_relativo_celda",
    "p3_ocupacion_equilibrio_pct", "p3_ocupacion_airbnb_pct",
    "dist_transporte_m", "modo_cercano", "amenities", "cochera_txt", "dias_publicacion_ambientes",
    "operacion", "estimacion_confiable", "fecha_scraping",
]

BOOLEANAS = ["en_presupuesto", "en_soporte_modelo", "universo_decision",
             "p1_comprar", "p1_comprar_con_entrada", "p2_no_dominada"]

# DISENO_TABLERO.md, seccion 1. El acento es solo para la banda y la propiedad
# seleccionada; nunca para texto.
COLORES = {
    "texto": "#30343F",
    "fondo": "#FFFFFF",
    "fondo_2": "#E8EEF7",
    "acento": "#FFD275",
    "contexto": "#778472",
    "principal": "#2F68B0",
    "alerta": "#C08A1E",
    "secundario": "#4A7F3A",
    "debajo_piso": "#2F68B0",
    "en_banda": "#B9BCC4",
    "sobre_techo": "#C08A1E",
    "seleccion": "#00A676",     # la propiedad elegida, en todas las vistas; solo para eso
    # Interfaz del rediseño: fondo de la pagina detras de las tarjetas blancas,
    # bordes y texto secundario (6:1 sobre blanco).
    "fondo_pagina": "#F3F5F9",
    "borde": "#E1E6EE",
    "texto_2": "#5B6170",
}

TIPOS = {"departamento": "Departamento", "ph": "PH", "casa": "Casa"}
# Escala divergente de DISENO_TABLERO.md: posicion respecto de la banda.
POSICIONES = {
    "debajo": (f"Debajo del piso (< {S.RETORNO_MINIMO_BANDA[0]:.2f}%)".replace(".", ","), COLORES["debajo_piso"]),
    "en_banda": ("Dentro de la banda", COLORES["en_banda"]),
    "sobre": (f"Sobre el techo (> {S.RETORNO_MINIMO_BANDA[1]:.2f}%)".replace(".", ","), COLORES["sobre_techo"]),
}
SIN_SOPORTE = ("ph", "casa")    # el modelo casi no tiene alquileres observados

# Los rangos son texto: el orden alfabetico no es el de tamanio ni el de edad.
ORDEN = {
    "superficie_rango": ["hasta 35", "36-55", "56-80", "81-120", "120+"],
    "antiguedad_rango": ["a estrenar", "1-5", "6-15", "16-30", "31-50", "50+"],
}


def cargar(ruta: str = DATASET) -> pd.DataFrame:
    """Ventas con estimacion confiable, solo con las columnas del tablero."""
    df = pd.read_csv(ruta, encoding="utf-8-sig", usecols=COLUMNAS, low_memory=False)
    df = df[(df["operacion"] == "venta") & (df["estimacion_confiable"] == 1)].copy()
    for c in BOOLEANAS:
        df[c] = df[c].fillna(False).astype(bool)
    df["barrio_nombre"] = df["barrio"].map(eda.nombre_barrio)
    return df.reset_index(drop=True)


@dataclass(frozen=True)
class Filtros:
    """Estado de la barra lateral. Una tupla vacia significa 'todos'."""
    presupuesto: tuple = S.PRESUPUESTO_USD
    tipo: str | None = "departamento"         # None: todos los tipos
    comunas: tuple = ()
    barrios: tuple = ()
    ambientes: tuple = ()
    superficies: tuple = ()
    antiguedades: tuple = ()

    @classmethod
    def sin_filtros(cls, df: pd.DataFrame) -> "Filtros":
        """Todo el rango de precios y todos los tipos: las cifras del informe."""
        return cls(presupuesto=(df["venta_usd"].min(), df["venta_usd"].max()), tipo=None)

    def con(self, **cambios) -> "Filtros":
        return replace(self, **cambios)


def filtrar(df: pd.DataFrame, f: Filtros) -> pd.DataFrame:
    m = df["venta_usd"].between(*f.presupuesto)
    if f.tipo is not None:
        m &= df["tipo_familia"] == f.tipo
    for col, valores in [("comuna", f.comunas), ("barrio", f.barrios), ("ambientes", f.ambientes),
                         ("superficie_rango", f.superficies), ("antiguedad_rango", f.antiguedades)]:
        if valores:
            m &= df[col].isin(valores)
    return df[m]


def opciones(df: pd.DataFrame, columna: str) -> list:
    """Valores de un filtro en su orden natural."""
    presentes = set(df[columna].dropna())
    if columna in ORDEN:
        return [v for v in ORDEN[columna] if v in presentes]
    return sorted(presentes)


def barrios_de(df: pd.DataFrame, comunas: tuple) -> list:
    """Barrios para el multiselect, acotados por las comunas elegidas."""
    sub = df[df["comuna"].isin(comunas)] if comunas else df
    return sorted(sub["barrio"].dropna().unique(), key=eda.nombre_barrio)


def kpis(df: pd.DataFrame) -> dict:
    """Las cuatro tarjetas de la pestana 1. Medianas, no promedios."""
    piso, _ = S.RETORNO_MINIMO_BANDA
    nan = float("nan")
    if df.empty:
        return {"n": 0, "neta_mediana": nan, "neta_min_mediana": nan, "neta_max_mediana": nan,
                "tir_mediana": nan, "pct_sobre_piso": nan, "pp_al_piso": nan}
    neta = df["rent_neta_pct"].median()
    return {
        "n": len(df),
        "neta_mediana": neta,
        "neta_min_mediana": df["neta_min_pct"].median(),
        "neta_max_mediana": df["neta_max_pct"].median(),
        "tir_mediana": df["tir_5a_pct"].median(),
        "pct_sobre_piso": (df["rent_neta_pct"] >= piso).mean() * 100,
        "pp_al_piso": neta - piso,
    }


def embudo(df: pd.DataFrame) -> list[tuple[str, int]]:
    """Universo de la decision -> neta central sobre el techo -> P1 -> P1 con entrada."""
    _, techo = S.RETORNO_MINIMO_BANDA
    u = df[df["universo_decision"]]
    central = u[u["rent_neta_pct"] > techo]
    p1 = central[central["p1_comprar"]]
    p1e = p1[p1["p1_comprar_con_entrada"]]
    return [
        ("Universo de la decisión", len(u)),
        ("Neta central sobre el techo", len(central)),
        ("Neta pesimista sobre el techo (P1)", len(p1)),
        ("TIR pesimista sobre el techo", len(p1e)),
    ]


def frase(k: dict) -> str:
    """La lectura en una linea; vacia si no quedan propiedades."""
    if k["n"] == 0:
        return ""
    pp = k["pp_al_piso"]
    sentido = "menos" if pp < 0 else "más"
    valor = f"{abs(pp):.2f}".replace(".", ",")
    return f"Con estos filtros, la propiedad típica rinde {valor} pp {sentido} que una ON en dólares."


def fechas_relevamiento(df: pd.DataFrame) -> str:
    """Dias del relevamiento, como en el diseño: '16 y 17-08-2026'."""
    dias = sorted(pd.to_datetime(df["fecha_scraping"], utc=True).dt.date.unique())
    if not dias:
        return ""
    if len({(d.month, d.year) for d in dias}) == 1:
        nums = [f"{d.day:02d}" for d in dias]
        lista = nums[0] if len(nums) == 1 else ", ".join(nums[:-1]) + " y " + nums[-1]
        return f"{lista}-{dias[0].month:02d}-{dias[0].year}"
    return ", ".join(d.strftime("%d-%m-%Y") for d in dias)


def cargar_ranking(df: pd.DataFrame, ruta: str = RANKING) -> pd.DataFrame:
    """
    ranking_barrios.csv con la banda mediana de la neta de cada barrio, ordenado por
    neta. No responde a los filtros: la banda sale de todas las ventas confiables,
    las mismas sobre las que se armo el ranking.
    """
    r = pd.read_csv(ruta, encoding="utf-8-sig")
    banda = df.groupby("barrio").agg(neta_min=("neta_min_pct", "median"),
                                     neta_max=("neta_max_pct", "median"))
    r = r.merge(banda, on="barrio", how="left")
    r["barrio_nombre"] = r["barrio"].map(eda.nombre_barrio)
    return r.sort_values("rent_neta").reset_index(drop=True)


def h1(df: pd.DataFrame) -> dict:
    """Medianas por barrio (m2 y bruta) y la pendiente de Theil-Sen, en pp por USD 500/m2."""
    g = df.groupby("barrio").agg(n=("rent_bruta_pct", "size"), m2=("venta_m2_usd", "median"),
                                 bruta=("rent_bruta_pct", "median"))
    b = g[g["n"] >= S.MIN_VENTAS_BARRIO].reset_index()
    b["barrio_nombre"] = b["barrio"].map(eda.nombre_barrio)
    nan = float("nan")
    if len(b) < 3:
        return {"barrios": b, "pendiente": nan, "ic": (nan, nan), "ordenada": nan}
    ts = stats.theilslopes(b["bruta"], b["m2"])
    return {"barrios": b, "pendiente": ts.slope * 500, "ic": (ts.low_slope * 500, ts.high_slope * 500),
            "ordenada": ts.intercept, "pendiente_m2": ts.slope}


def posicion_banda(valores: pd.Series) -> pd.Series:
    """Categoria de la escala divergente; sin dato queda sin dato."""
    piso, techo = S.RETORNO_MINIMO_BANDA
    cat = pd.Series(np.select([valores < piso, valores > techo], ["debajo", "sobre"], "en_banda"),
                    index=valores.index, dtype=object)
    return cat.where(valores.notna())


def sin_coordenadas(df: pd.DataFrame) -> int:
    return int((df["latitud"].isna() | df["longitud"].isna()).sum())


def p1_tabla(df: pd.DataFrame) -> pd.DataFrame:
    """Las que pasan P1 dentro del universo de la decision: 'a verificar', no 'comprar'."""
    p1 = df[df["universo_decision"] & df["p1_comprar"]]
    return p1.sort_values(["neta_min_pct", "id_aviso"], ascending=[False, True]).reset_index(drop=True)


def descuento_p1(p1: pd.DataFrame) -> int | None:
    """Cuanto menos cuesta el m2 de las P1 que su celda (mediana), redondeado a 5 puntos."""
    if p1.empty:
        return None
    return int(round((1 - p1["m2_relativo_celda"].median()) * 100 / 5) * 5)


def frontera_p2(df: pd.DataFrame) -> pd.DataFrame:
    """
    La frontera P2 tal como la guarda decision.py, ordenada por ancho de banda (la mas
    angosta primero). NUNCA por rentabilidad: entre estas ninguna le gana con claridad
    a otra (GUIA_TABLERO.md). Con filtros es el subconjunto de la frontera del universo,
    no la frontera recalculada.
    """
    fr = df[df["universo_decision"] & df["p2_no_dominada"]].copy()
    fr["ancho"] = fr["neta_max_pct"] - fr["neta_min_pct"]
    return fr.sort_values(["ancho", "id_aviso"]).reset_index(drop=True)


def fila(df: pd.DataFrame, id_aviso) -> pd.Series | None:
    """La propiedad seleccionada, si sigue en la vista filtrada."""
    if id_aviso is None:
        return None
    sub = df[df["id_aviso"] == id_aviso]
    return None if sub.empty else sub.iloc[0]


# --- Pestana 4: tradicional contra temporal (tablas precalculadas, sin filtros) -----
P3 = os.path.join(RAIZ, "data", "processed", "decision_p3.csv")
TEMPORAL = os.path.join(RAIZ, "data", "processed", "temporal_vs_tradicional.csv")

# DISENO_TABLERO.md: tercerizada en el dato principal, autogestionada en el secundario.
GESTIONES = {"tercerizada": ("Tercerizada", COLORES["principal"]),
             "autogestionado": ("Autogestionada", COLORES["secundario"])}


def cargar_p3(ruta: str = P3) -> pd.DataFrame:
    return pd.read_csv(ruta, encoding="utf-8-sig")


def vacancias(p3: pd.DataFrame) -> list:
    return sorted(p3["vacancia_tradicional_pct"].unique().tolist())


def p3_vacancia(p3: pd.DataFrame, vacancia: float) -> pd.DataFrame:
    """Celdas donde gana el temporal segun la ocupacion, para una vacancia del tradicional."""
    sub = p3[p3["vacancia_tradicional_pct"] == vacancia]
    return sub.sort_values(["gestion", "ocupacion_sostenible_pct"]).reset_index(drop=True)


def equilibrio(sub: pd.DataFrame) -> dict:
    """Ocupacion de equilibrio mediana por gestion: con ella el temporal empata."""
    return sub.groupby("gestion")["equilibrio_mediano_pct"].first().to_dict()


def ocupacion_airbnb(ruta: str = TEMPORAL) -> float:
    """Mediana entre celdas de la ocupacion que estima Inside Airbnb."""
    return float(pd.read_csv(ruta, encoding="utf-8-sig")["ocupacion_mediana_pct"].median())


# --- Pestana 5: supuestos y alcance (tablas precalculadas, sin filtros) -------------
SENSIBILIDAD = os.path.join(RAIZ, "data", "processed", "decision_sensibilidad.csv")
EXTERNAS = os.path.join(RAIZ, "data", "external")
SUPUESTOS_BASE = ["vacancia", "gastos_sin_abl", "abl", "entrada", "umbral", "margen"]
NOMBRES_ABL = {"plano": "ABL plano", "segmentado": "ABL segmentado", "segmentado_tope": "ABL con tope"}

# (nombre, archivo en data/external/, columna del periodo que cubre o None)
FUENTES = [
    ("Estadística Ciudad: m² publicado", "estadistica_ciudad_m2_barrio.csv", "trimestre"),
    ("Estadística Ciudad: tiempo de publicación", "estadistica_ciudad_tiempo_publicacion.csv", "trimestre"),
    ("Colegio de Escribanos", "colegio_escribanos_mensual.csv", "mes"),
    ("Inside Airbnb", "airbnb_barrio_dormitorios.csv", "snapshot"),
    ("Censo 2022", "censo_departamentos_comuna.csv", None),
    ("BA Data: transporte", "transporte_estaciones.csv", None),
    ("BA Data: espacios verdes", "espacios_verdes.csv", None),
]


def _coma(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _escenario(f) -> str:
    p = f["parametro"]
    if p == "vacancia":
        return f"Vacancia {_coma(f['vacancia'])}%"
    if p == "gastos sin ABL":
        return f"Gastos sin ABL {_coma(f['gastos_sin_abl'])}%"
    if p == "ABL":
        return NOMBRES_ABL.get(f["abl"], f"ABL {f['abl']}")
    if p == "costos de entrada":
        return f"Costos de entrada: {f['entrada']}"
    if p == "banda de retorno":
        return f"Umbral {_coma(f['umbral'])}%"
    if p == "margen por liquidez":
        return f"Margen {_coma(f['margen'])} pp"
    return str(p).capitalize()


def cargar_sensibilidad(ruta: str = SENSIBILIDAD) -> pd.DataFrame:
    """Los 22 escenarios de decision.py, con su etiqueta y la marca de los iguales a la base."""
    s = pd.read_csv(ruta, encoding="utf-8-sig")
    base = s.loc[s["parametro"] == "base", SUPUESTOS_BASE].iloc[0]
    s["es_base"] = (s[SUPUESTOS_BASE] == base).all(axis=1)
    s["escenario"] = s.apply(_escenario, axis=1)
    return s


def fuentes(carpeta: str = EXTERNAS) -> pd.DataFrame:
    """Periodo que cubre y fecha de descarga de cada fuente externa, leidos de sus tablas."""
    filas = []
    for nombre, archivo, col in FUENTES:
        t = pd.read_csv(os.path.join(carpeta, archivo), encoding="utf-8-sig", low_memory=False)
        filas.append({"fuente": nombre,
                      "periodo": str(t[col].astype(str).max()) if col else "",
                      "descarga": str(t["fecha_descarga"].astype(str).max())})
    return pd.DataFrame(filas)
