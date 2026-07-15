import os
import re
import unicodedata
from pathlib import Path

import pandas as pd
import pdfplumber


RANGOS_SIEFORE = {
    "60-64": "SB 60-64",
    "65-69": "SB 65-69",
    "70-74": "SB 70-74",
    "75-79": "SB 75-79",
    "80-84": "SB 80-84",
    "85-89": "SB 85-89",
    "90-94": "SB 90-94",
    "95-99": "SB 95-99",
}

PALABRAS_CONTEXTO_PORTFOLIO = (
    "SB",
    "SIEFORE",
    "BASICA",
    "BASICO",
    "FONDO",
    "PORTFOLIO",
)

FONDO_MAPPING = {
    "SB 60-64": "INVER60",
    "SB 65-69": "INVER65",
    "SB 70-74": "INVER70",
    "SB 75-79": "INVER75",
    "SB 80-84": "INVER80",
    "SB 85-89": "INVER85",
    "SB 90-94": "INVER90",
    "SB 95-99": "INVER95",
    "SB INICIAL": "INVERINICIAL",
    "SB PENSIONES": "INVER00",
}


def limpiar_texto_pdf(texto):
    if not texto or pd.isna(texto):
        return ""

    texto = str(texto)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    texto = texto.replace("\u00a0", " ")
    texto = re.sub(r"[‐‑‒–—―_]", "-", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip().upper()


def _tiene_contexto_portfolio(texto_limpio):
    compacto = re.sub(r"[^A-Z0-9]", "", texto_limpio)
    return any(palabra in compacto for palabra in PALABRAS_CONTEXTO_PORTFOLIO)


def _es_texto_corto_de_rango(texto_limpio):
    alfanumerico = re.sub(r"[^A-Z0-9]", "", texto_limpio)
    return len(alfanumerico) <= 8


def _patron_rango(rango):
    inicio, fin = rango.split("-")
    inicio_flexible = r"\s*".join(inicio)
    fin_flexible = r"\s*".join(fin)
    return rf"(?<!\d){inicio_flexible}\s*[- ]?\s*{fin_flexible}(?!\d)"


def _contiene_pensiones(compacto):
    return "PENSION" in compacto or bool(re.search(r"P[A-Z]{0,4}E[A-Z]{0,4}N[A-Z]{0,4}S[A-Z]{0,4}I[A-Z]{0,4}O[A-Z]{0,4}N[A-Z]{0,4}E[A-Z]{0,4}S", compacto))


def normalizar_portfolio(texto):
    texto_limpio = limpiar_texto_pdf(texto)
    if not texto_limpio:
        return None

    compacto = re.sub(r"[^A-Z0-9]", "", texto_limpio)

    if re.search(r"\bFECHA\s+INICIAL\b", texto_limpio):
        texto_limpio = re.sub(r"\bFECHA\s+INICIAL\b", "FECHA", texto_limpio)
        compacto = re.sub(r"[^A-Z0-9]", "", texto_limpio)

    if "INICIAL" in compacto and re.search(r"\b(SB|SIEFORE|BASICA|BASICO)\b.*\bINICIAL\b|\bINICIAL\b.*\b(SB|SIEFORE|BASICA|BASICO)\b", texto_limpio):
        return "SB INICIAL"

    if (
        _contiene_pensiones(compacto)
        or ("ASICADE" in compacto and "CUENTA" in compacto)
        or re.search(r"\bBASICA\s+DE\b", texto_limpio)
        or re.search(r"\bCERO\b", texto_limpio)
        or re.search(r"\bSB\s*0\b", texto_limpio)
        or re.search(r"\bBASICA\s*0\b", texto_limpio)
        or compacto in {"0", "SB0", "CERO", "SBCERO", "BASICACERO"}
    ):
        return "SB PENSIONES"

    tiene_contexto = _tiene_contexto_portfolio(texto_limpio)
    es_corto = _es_texto_corto_de_rango(texto_limpio)
    for rango, nombre_std in RANGOS_SIEFORE.items():
        if re.search(_patron_rango(rango), texto_limpio) and (tiene_contexto or es_corto):
            return nombre_std

    return None


def detectar_portfolio_en_lineas(lineas, limite=30, ventana=3):
    lineas_limpias = [limpiar_texto_pdf(linea) for linea in lineas[:limite]]

    for linea in lineas_limpias:
        portfolio = normalizar_portfolio(linea)
        if portfolio:
            return portfolio

    for idx in range(len(lineas_limpias)):
        bloque = " ".join(lineas_limpias[idx : idx + ventana])
        portfolio = normalizar_portfolio(bloque)
        if portfolio:
            return portfolio

    return None


def extraer_importes(texto):
    importes = []
    for match in re.finditer(r"(?:\$|MXN|MXP|USD)?\s*([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", texto, re.IGNORECASE):
        try:
            importes.append(float(match.group(1).replace(",", "")))
        except ValueError:
            continue
    return importes


def seleccionar_importe_interes(texto):
    importes = extraer_importes(texto)
    if not importes:
        return None

    texto_limpio = limpiar_texto_pdf(texto)
    if "TASA" in texto_limpio and len(importes) > 1 and importes[0] <= 100:
        return importes[1]

    return importes[0]


def bloques_movimientos_bbva(lineas):
    bloques = []
    actual = []

    for linea in lineas:
        if re.match(r"^\s*\d{10}\b", linea):
            if actual:
                bloques.append(actual)
            actual = [linea]
        elif actual:
            actual.append(linea)

    if actual:
        bloques.append(actual)

    return bloques


def portfolio_a_fondo(portfolio):
    return FONDO_MAPPING.get(portfolio, portfolio)


def detectar_banco_pdf(ruta_pdf):
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            texto = ""
            for page in pdf.pages[:2]:
                texto += (page.extract_text() or "") + "\n"
    except Exception:
        return None

    texto_upper = texto.upper()
    nombre_archivo = os.path.basename(ruta_pdf).upper()

    if "SCOTIABANK" in texto_upper or "SCOTIABANK" in nombre_archivo or "SCOTIA" in nombre_archivo:
        return "SCOTIABANK"
    if "BBVA" in texto_upper or "BBVA" in nombre_archivo:
        return "BBVA"
    if (
        "BANREGIO" in texto_upper
        or "BANREGIO" in nombre_archivo
        or "DETALLE DE MOVIMIENTOS CUENTA DE CHEQUES" in texto_upper
    ):
        return "BANREGIO"

    return None


def leer_bbva_pdf(ruta_pdf):
    with pdfplumber.open(ruta_pdf) as pdf:
        lineas = []
        for page in pdf.pages:
            texto = page.extract_text() or ""
            lineas.extend(texto.splitlines())

    texto_head = " ".join(lineas[:30]).upper()
    if "USD" in texto_head:
        moneda = "USD"
        patron_importe = r"USD\s+([\d,]+\.\d{2})"
    else:
        moneda = "MXN"
        patron_importe = r"MX[NP]\s+([\d,]+\.\d{2})"

    filas = []
    for bloque_lineas in bloques_movimientos_bbva(lineas):
        bloque = " ".join(bloque_lineas)
        bloque_limpio = limpiar_texto_pdf(bloque)

        if "INTERES" not in bloque_limpio and "RENDIMIENTO" not in bloque_limpio:
            continue

        portfolio = normalizar_portfolio(bloque)
        if not portfolio:
            continue

        importe = None
        for linea in bloque_lineas:
            match = re.search(patron_importe, linea)
            if match:
                importe = float(match.group(1).replace(",", ""))
                break

        if importe and importe > 0:
            filas.append(
                {
                    "Portfolio": portfolio,
                    "Intereses": importe,
                    "Moneda": moneda,
                    "Banco": "BBVA",
                }
            )

    if not filas:
        return pd.DataFrame(columns=["Portfolio", "Intereses", "Moneda", "Banco"])

    df = pd.DataFrame(filas)
    df = df.groupby(["Portfolio", "Moneda"], as_index=False)["Intereses"].sum()
    df["Banco"] = "BBVA"
    return df


def leer_banregio_pdf(ruta_pdf):
    with pdfplumber.open(ruta_pdf) as pdf:
        filas = []

        for page in pdf.pages:
            texto = page.extract_text() or ""
            lineas = texto.splitlines()

            portfolio = detectar_portfolio_en_lineas(lineas, limite=25, ventana=4)

            if not portfolio:
                continue

            for idx, linea in enumerate(lineas):
                linea_limpia = limpiar_texto_pdf(linea)
                if "INTERES" in linea_limpia or "RENDIMIENTO" in linea_limpia:
                    bloque = " ".join(lineas[idx : idx + 3])
                    importe = seleccionar_importe_interes(bloque)
                    if importe:
                        filas.append(
                            {
                                "Portfolio": portfolio,
                                "Intereses": importe,
                                "Moneda": None,
                                "Banco": "Banregio",
                            }
                        )
                        break

    if not filas:
        return pd.DataFrame(columns=["Portfolio", "Intereses", "Moneda", "Banco"])

    nombre_archivo = os.path.basename(ruta_pdf).upper()
    moneda = "USD" if "USD" in nombre_archivo else "MXN"
    for fila in filas:
        fila["Moneda"] = moneda

    return pd.DataFrame(filas)


def leer_scotiabank_pdf(ruta_pdf):
    with pdfplumber.open(ruta_pdf) as pdf:
        filas = []

        for page in pdf.pages:
            texto = page.extract_text() or ""
            lineas = texto.splitlines()

            portfolio = detectar_portfolio_en_lineas(lineas, limite=40, ventana=4)

            if not portfolio:
                continue

            moneda = None
            for linea in lineas[:20]:
                linea_limpia = limpiar_texto_pdf(linea)
                if "MONEDA" in linea_limpia:
                    if "USD" in linea_limpia:
                        moneda = "USD"
                    elif "MXN" in linea_limpia:
                        moneda = "MXN"
                    break
            if not moneda:
                nombre_archivo = os.path.basename(ruta_pdf).upper()
                moneda = "USD" if "USD" in nombre_archivo else "MXN"

            importe = None
            for idx, linea in enumerate(lineas):
                linea_limpia = limpiar_texto_pdf(linea)
                if "RENDIMIENTO" in linea_limpia or "INTERES" in linea_limpia:
                    bloque = " ".join(lineas[idx : idx + 3])
                    importe = seleccionar_importe_interes(bloque)
                    if importe:
                        break

            if importe and importe > 0:
                filas.append(
                    {
                        "Portfolio": portfolio,
                        "Intereses": importe,
                        "Moneda": moneda,
                        "Banco": "Scotiabank",
                    }
                )

    if not filas:
        return pd.DataFrame(columns=["Portfolio", "Intereses", "Moneda", "Banco"])

    return pd.DataFrame(filas)


def leer_estado_cuenta_pdf(ruta_pdf):
    if not os.path.exists(ruta_pdf):
        return pd.DataFrame()

    banco = detectar_banco_pdf(ruta_pdf)
    if banco == "BBVA":
        return leer_bbva_pdf(ruta_pdf)
    if banco == "BANREGIO":
        return leer_banregio_pdf(ruta_pdf)
    if banco == "SCOTIABANK":
        return leer_scotiabank_pdf(ruta_pdf)
    return pd.DataFrame(columns=["Portfolio", "Intereses", "Moneda", "Banco"])


def procesar_lote_pdfs(archivos):
    todos_df = []
    errores = []

    for archivo in archivos:
        try:
            df = leer_estado_cuenta_pdf(str(archivo))
            if df.empty:
                errores.append(f"No se encontraron intereses en {Path(archivo).name}")
            else:
                df["Archivo"] = Path(archivo).name
                todos_df.append(df)
        except Exception as exc:
            errores.append(f"{Path(archivo).name}: {exc}")

    if not todos_df:
        return pd.DataFrame(columns=["Portfolio", "Intereses", "Moneda", "Banco", "Archivo"]), errores

    return pd.concat(todos_df, ignore_index=True), errores
