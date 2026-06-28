import os
import re
from pathlib import Path

import pandas as pd
import pdfplumber


PORTFOLIO_MAPPING = {
    r"(?i)(siefore\s+)?invercap\s+basica\s+60[- ]64": "SB 60-64",
    r"(?i)SB\s*60[- ]64": "SB 60-64",
    r"(?i)60.?64": "SB 60-64",
    r"(?i)(siefore\s+)?invercap\s+basica\s+65[- ]69": "SB 65-69",
    r"(?i)SB\s*65[- ]69": "SB 65-69",
    r"(?i)65.?69": "SB 65-69",
    r"(?i)(siefore\s+)?invercap\s+basica\s+70[- ]74": "SB 70-74",
    r"(?i)SB\s*70[- ]74": "SB 70-74",
    r"(?i)70.?74": "SB 70-74",
    r"(?i)(siefore\s+)?invercap\s+basica\s+75[- ]79": "SB 75-79",
    r"(?i)SB\s*75[- ]79": "SB 75-79",
    r"(?i)75.?79": "SB 75-79",
    r"(?i)(siefore\s+)?invercap\s+basica\s+80[- ]84": "SB 80-84",
    r"(?i)SB\s*80[- ]84": "SB 80-84",
    r"(?i)80.?84": "SB 80-84",
    r"(?i)(siefore\s+)?invercap\s+basica\s+85[- ]89": "SB 85-89",
    r"(?i)SB\s*85[- ]89": "SB 85-89",
    r"(?i)85.?89": "SB 85-89",
    r"(?i)(siefore\s+)?invercap\s+basica\s+90[- ]94": "SB 90-94",
    r"(?i)SB\s*90[- ]94": "SB 90-94",
    r"(?i)90.?94": "SB 90-94",
    r"(?i)(siefore\s+)?invercap\s+basica\s+95[- ]99": "SB 95-99",
    r"(?i)SB\s*95[- ]99": "SB 95-99",
    r"(?i)95.?99": "SB 95-99",
    r"(?i)(siefore\s+)?invercap\s+basica\s+inicial": "SB INICIAL",
    r"(?i)SB\s+INICIAL": "SB INICIAL",
    r"(?i)(siefore\s+)?invercap\s+basica\s+de\s+pensiones": "SB PENSIONES",
    r"(?i)SB\s+PENSIONES": "SB PENSIONES",
}

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
    "SB PENSIONES": "INVERPENSIONES",
}


def normalizar_portfolio(texto):
    if not texto or pd.isna(texto):
        return None

    texto = str(texto).strip()
    for patron, nombre_std in PORTFOLIO_MAPPING.items():
        if re.search(patron, texto):
            return nombre_std
    return texto


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

    importes_por_linea = {}
    for idx, linea in enumerate(lineas):
        match = re.search(patron_importe, linea)
        if match:
            importes_por_linea[idx] = float(match.group(1).replace(",", ""))

    filas = []
    for i, linea in enumerate(lineas):
        alias_match = re.search(
            r"SB\s+(?:(\d{2})[- ](\d{2})|INICIAL|PENSIONES)",
            linea,
            re.IGNORECASE,
        )
        if not alias_match:
            continue

        portfolio = normalizar_portfolio(alias_match.group(0).strip())
        importe = None
        for offset in range(-2, 3):
            idx = i + offset
            if idx in importes_por_linea:
                importe = importes_por_linea[idx]
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

            portfolio = None
            for linea in lineas[:15]:
                candidato = normalizar_portfolio(linea)
                if candidato and str(candidato).startswith("SB"):
                    portfolio = candidato
                    break

            if not portfolio:
                continue

            for linea in lineas:
                if "interes" in linea.lower() or "rendimiento" in linea.lower():
                    match = re.search(r"\$\s*([\d,]+\.\d{2})", linea)
                    if match:
                        filas.append(
                            {
                                "Portfolio": portfolio,
                                "Intereses": float(match.group(1).replace(",", "")),
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

            portfolio = None
            for linea in lineas[:25]:
                candidato = normalizar_portfolio(" ".join(linea.split()))
                if candidato and str(candidato).startswith("SB"):
                    portfolio = candidato
                    break

            if not portfolio:
                rangos_validos = {"60-64", "65-69", "70-74", "75-79", "80-84", "85-89", "90-94", "95-99"}
                for linea in lineas[:30]:
                    match = re.search(r"(\d{2})[- ](\d{2})", linea)
                    if match:
                        rango = f"{match.group(1)}-{match.group(2)}"
                        if rango in rangos_validos:
                            portfolio = normalizar_portfolio(f"SB {rango}")
                            break

            if not portfolio:
                continue

            moneda = None
            for linea in lineas[:20]:
                if "Moneda" in linea:
                    if "USD" in linea.upper():
                        moneda = "USD"
                    elif "MXN" in linea.upper():
                        moneda = "MXN"
                    break
            if not moneda:
                nombre_archivo = os.path.basename(ruta_pdf).upper()
                moneda = "USD" if "USD" in nombre_archivo else "MXN"

            importe = None
            for linea in lineas:
                if "RENDIMIENTO" in linea.upper() and "TASA" in linea.upper():
                    matches = re.findall(r"([\d,]+\.\d{2})", linea)
                    if matches:
                        importe = float(matches[0].replace(",", ""))
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
