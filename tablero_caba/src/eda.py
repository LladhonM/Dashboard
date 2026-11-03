#!/usr/bin/env python
"""
eda.py — Estadistica robusta y estilo grafico compartido por los notebooks.

POR QUE UN MODULO Y NO CODIGO EN EL NOTEBOOK
--------------------------------------------
Tres notebooks que definen cada uno su paleta terminan con tres paletas
distintas, y un informe donde el mismo barrio cambia de color entre paginas.
Aca vive todo lo que tiene que ser identico entre notebooks: los colores, el
formato de los ejes, la funcion que guarda las figuras y la que calcula los
estadisticos de resumen.

POR QUE ESTADISTICA "ROBUSTA"
-----------------------------
La media y el desvio estandar describen bien una distribucion simetrica. Las
tres variables centrales de este trabajo —precio de venta, precio por m2 y
rentabilidad— tienen cola derecha larga y asimetria positiva fuerte. En esos
casos la media queda por encima de la mayoria de los datos y el desvio se
infla. Por eso cada resumen reporta la mediana junto a la media, el IQR y la
MAD junto al desvio, y la asimetria explicita para que el lector sepa cuanto
se estan separando.
"""

from __future__ import annotations

import os

import matplotlib as mpl
import numpy as np
import pandas as pd
import seaborn as sns


# ==========================================================================
# PALETA
# ==========================================================================

# Instancia de referencia del sistema de visualizacion, sin modificar. Solo se
# usan los tres primeros slots categoricos: son los unicos que el sistema
# certifica para graficos donde TODOS los pares de series compiten a la vez
# (dispersion, burbujas, mapas de calor por categoria), no solo los adyacentes.
# Mas de tres series se pliegan en "otros" o se separan en paneles.
SERIE_1 = "#2a78d6"   # azul
SERIE_2 = "#eb6834"   # naranja
SERIE_3 = "#1baf7a"   # aqua
CATEGORICA = [SERIE_1, SERIE_2, SERIE_3]

# Magnitud continua: un solo tono, claro a oscuro. Nunca arcoiris: un arcoiris
# inventa saltos de categoria donde la variable es continua.
SECUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# Polaridad (correlaciones): dos polos opuestos con gris —no un tono— en el
# medio, para que el cero se lea como "nada" y no como un valor mas.
DIVERGENTE = ["#0d366b", "#256abf", "#86b6ef", "#f0efec", "#f0a3a3", "#d03b3b", "#8f2020"]

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_3 = "#8a8880"
GRILLA = "#e5e4e0"

# Estado. Reservado: nunca se usa como "serie 4".
CRITICO = "#d03b3b"

CMAP_SEC = mpl.colors.LinearSegmentedColormap.from_list("sec", SECUENCIAL)
CMAP_DIV = mpl.colors.LinearSegmentedColormap.from_list("div", DIVERGENTE)

DIR_GRAFICOS = "../graficos"


def estilo() -> None:
    """Aplica el estilo a matplotlib. Se llama una vez por notebook."""
    sns.set_theme(style="white")
    mpl.rcParams.update({
        "figure.facecolor": SUPERFICIE,
        "axes.facecolor": SUPERFICIE,
        "savefig.facecolor": SUPERFICIE,
        "figure.dpi": 110,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "600",
        "axes.titlelocation": "left",
        "axes.titlepad": 12,
        "axes.labelsize": 10,
        "axes.labelcolor": TINTA_2,
        "axes.edgecolor": GRILLA,
        "axes.linewidth": 1.0,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRILLA,
        "grid.linewidth": 0.8,
        "text.color": TINTA,
        "xtick.color": TINTA_2,
        "ytick.color": TINTA_2,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "lines.linewidth": 2.0,
        "lines.markersize": 8,
        "patch.linewidth": 0,
    })


def guardar(fig, n: int, nombre: str) -> str:
    """
    Guarda la figura en graficos/ con numero de orden.

    El numero va en el nombre del archivo para que el orden del directorio
    coincida con el del informe y no haya que adivinar cual es cual.
    """
    os.makedirs(DIR_GRAFICOS, exist_ok=True)
    path = os.path.join(DIR_GRAFICOS, f"{n:02d}_{nombre}.png")
    fig.savefig(path)
    print(f"guardado: {path}")
    return path


def titulo(ax, texto: str, subtitulo: str = "") -> None:
    """
    Titulo en dos niveles: que se mira arriba, que dice abajo.

    El subtitulo lleva la conclusion en palabras. Un grafico cuyo titulo es
    solo el nombre de la variable obliga al lector a redescubrir el hallazgo.

    El pad del titulo se agranda cuando hay subtitulo: con el pad por defecto
    los dos textos se dibujan a la misma altura y se superponen.
    """
    if subtitulo:
        ax.set_title(texto, color=TINTA, pad=30)
        ax.text(0, 1.012, subtitulo, transform=ax.transAxes,
                fontsize=9.5, color=TINTA_2, va="bottom")
    else:
        ax.set_title(texto, color=TINTA)


def sin_grilla_y(ax) -> None:
    ax.grid(False, axis="y")
    ax.grid(True, axis="x", color=GRILLA, linewidth=0.8)


# ==========================================================================
# ESTADISTICA ROBUSTA
# ==========================================================================

def resumen_robusto(df: pd.DataFrame, columnas: list) -> pd.DataFrame:
    """
    Tabla de resumen que pone lado a lado los estadisticos clasicos y los
    robustos, mas la asimetria y la curtosis que explican su diferencia.

    Columnas devueltas:
        n, nulos%          cuantos datos hay realmente detras del resumen
        media, mediana     el par que revela la asimetria al compararse
        desvio, IQR, MAD   dispersion clasica y sus dos versiones robustas
        CV                 desvio / media: dispersion comparable entre escalas
        asimetria          >0 cola derecha larga. >1 se considera fuerte
        curtosis           exceso sobre la normal. >3 hay outliers pesados
        p5, p25, p75, p95  la forma de la distribucion sin suponer nada
    """
    filas = []
    descartadas = []
    for c in columnas:
        s = pd.to_numeric(df[c], errors="coerce")
        v = s.dropna()
        if len(v) < 3:
            # Una columna de texto se convierte entera a NaN y desaparece de la
            # tabla. Descartarla esta bien; hacerlo en silencio no, porque el
            # lector cree que la pidio y la esta viendo.
            descartadas.append(c)
            continue
        q1, q3 = v.quantile(0.25), v.quantile(0.75)
        filas.append({
            "variable": c,
            "n": len(v),
            "nulos_%": round(s.isna().mean() * 100, 1),
            "media": v.mean(),
            "mediana": v.median(),
            "desvio": v.std(),
            "IQR": q3 - q1,
            "MAD": (v - v.median()).abs().median(),
            "CV": v.std() / v.mean() if v.mean() else np.nan,
            "asimetria": v.skew(),
            "curtosis": v.kurtosis(),
            "p5": v.quantile(0.05),
            "p25": q1,
            "p75": q3,
            "p95": v.quantile(0.95),
        })
    if descartadas:
        print(f"resumen_robusto: {len(descartadas)} columnas descartadas por no ser "
              f"numericas o tener menos de 3 valores: {', '.join(descartadas)}")
    return pd.DataFrame(filas).set_index("variable").round(2)


# El dataset guarda los barrios en minuscula y sin tildes porque asi los
# normaliza la limpieza, y asi tienen que quedar para que los joins funcionen.
# Para mostrarlos en un texto o en un eje hace falta el nombre oficial. Estas
# son las unicas nueve excepciones que `.title()` no resuelve: ocho por tilde y
# "villa del parque", donde el articulo va en minuscula.
BARRIOS_NOMBRE = {
    "agronomia": "Agronomía",
    "constitucion": "Constitución",
    "nunez": "Núñez",
    "san cristobal": "San Cristóbal",
    "san nicolas": "San Nicolás",
    "velez sarsfield": "Vélez Sarsfield",
    "villa del parque": "Villa del Parque",
    "villa ortuzar": "Villa Ortúzar",
    "villa pueyrredon": "Villa Pueyrredón",
}


def nombre_barrio(barrio) -> str:
    """Nombre oficial del barrio para mostrar. No toca el dato, solo la vista."""
    if barrio is None or (isinstance(barrio, float) and pd.isna(barrio)):
        return "sin dato"
    clave = str(barrio).strip().lower()
    return BARRIOS_NOMBRE.get(clave, clave.title())


def nombres_barrio(barrios) -> list:
    """La version lista, para ejes y enumeraciones."""
    return [nombre_barrio(b) for b in barrios]


def frecuencias(serie: pd.Series, top: int = 15) -> pd.DataFrame:
    """Tabla de frecuencias absolutas, relativas y acumuladas."""
    vc = serie.value_counts(dropna=False).head(top)
    out = pd.DataFrame({
        "n": vc,
        "%": (vc / len(serie) * 100).round(2),
    })
    out["% acum"] = out["%"].cumsum().round(2)
    return out


def por_barrio(df: pd.DataFrame, col: str, minimo: int = 30) -> pd.DataFrame:
    """
    Agregado por barrio con el corte de tamaño minimo aplicado y declarado.

    El corte importa: una mediana calculada sobre 4 avisos no es una mediana
    de barrio, es una anecdota. Se devuelve tambien cuantos barrios quedaron
    afuera para poder decirlo en el informe.
    """
    g = df.groupby("barrio")[col].agg(["count", "median", "mean", "std",
                                       lambda s: s.quantile(.25),
                                       lambda s: s.quantile(.75)])
    g.columns = ["n", "mediana", "media", "desvio", "p25", "p75"]
    g["IQR"] = (g["p75"] - g["p25"]).round(2)
    return g[g["n"] >= minimo].sort_values("mediana", ascending=False).round(2)


def matriz_correlacion(df: pd.DataFrame, columnas: list,
                       metodo: str = "spearman") -> pd.DataFrame:
    """
    Correlacion por Spearman y no por Pearson.

    Pearson mide relacion LINEAL y se deja arrastrar por los valores extremos,
    que en precios inmobiliarios son muchos. Spearman trabaja sobre rangos:
    captura cualquier relacion monotona y es inmune a la escala. Para las
    dummies (0/1) Spearman coincide con la correlacion punto-biserial de
    rangos, que es lo que corresponde comparar contra una continua.

    Las columnas no numericas se descartan y se avisa. En pandas 3 el texto
    tiene dtype propio (no object) y .corr() revienta con "could not convert
    string to float" en vez de ignorarlo.
    """
    numericas = [c for c in columnas if pd.api.types.is_numeric_dtype(df[c])]
    fuera = [c for c in columnas if c not in numericas]
    if fuera:
        print(f"matriz_correlacion: {len(fuera)} columnas descartadas por no ser "
              f"numericas: {', '.join(fuera)}")
    return df[numericas].corr(method=metodo)


# ==========================================================================
# COMPARAR SEMEJANTES
# ==========================================================================
#
# Una diferencia de renta entre deptos con y sin amenities, medida sobre todo
# el mercado, mezcla el efecto de los amenities con el del barrio y el tamanio:
# los edificios con amenities se concentran en zonas caras. Estas funciones
# comparan dentro de celdas de propiedades semejantes (un "estrato") y recien
# despues agregan.

def mediana_ponderada(valores, pesos) -> float:
    """Mediana ponderada: el valor que deja la mitad del peso a cada lado."""
    v = np.asarray(valores, dtype=float)
    w = np.asarray(pesos, dtype=float)
    m = ~np.isnan(v) & ~np.isnan(w) & (w > 0)
    if not m.any():
        return np.nan
    v, w = v[m], w[m]
    orden = np.argsort(v)
    v, w = v[orden], w[orden]
    acum = np.cumsum(w)
    return float(v[np.searchsorted(acum, acum[-1] / 2)])


def efecto_estratificado(df: pd.DataFrame, grupo: str, respuesta: str,
                         estrato: list, minimo: int = 5) -> pd.DataFrame:
    """
    Diferencia de medianas de `respuesta` entre grupo==1 y grupo==0, calculada
    DENTRO de cada celda del estrato.

    Una celda entra solo si cada grupo tiene al menos `minimo` observaciones:
    una mediana de dos avisos contra una de cuarenta no es una comparacion.
    El peso de cada celda es el tamanio del grupo mas chico, porque es el que
    limita cuanto se puede confiar en la diferencia.
    """
    filas = []
    for clave, g in df.groupby(estrato, observed=True):
        uno = g.loc[g[grupo] == 1, respuesta].dropna()
        cero = g.loc[g[grupo] == 0, respuesta].dropna()
        if len(uno) >= minimo and len(cero) >= minimo:
            clave = clave if isinstance(clave, tuple) else (clave,)
            filas.append({**dict(zip(estrato, clave)),
                          "n_1": len(uno), "n_0": len(cero),
                          "mediana_1": uno.median(), "mediana_0": cero.median(),
                          "diferencia": uno.median() - cero.median(),
                          "peso": min(len(uno), len(cero))})
    return pd.DataFrame(filas)
