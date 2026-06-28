from datetime import date, timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from pathlib import Path

import pandas as pd
import streamlit as st

from parser_intereses import portfolio_a_fondo, procesar_lote_pdfs


st.set_page_config(
    page_title="Intereses",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        :root {
            --brand: #0f766e;
            --brand-dark: #134e4a;
            --ink: #1f2937;
            --muted: #667085;
            --line: #d8e2e7;
            --surface: #ffffff;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(15, 118, 110, .10), transparent 30rem),
                linear-gradient(180deg, #f7faf9 0%, #eef4f3 100%);
        }
        .block-container { padding-top: 2rem; max-width: 1180px; }
        [data-testid="stMetric"] {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 14px 16px;
            box-shadow: 0 1px 2px rgba(16, 24, 40, .04);
        }
        [data-testid="stFileUploader"] {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 10px 14px;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 8px;
            overflow: hidden;
        }
        .app-header {
            align-items: center;
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
        }
        .app-mark {
            align-items: center;
            background: var(--brand-dark);
            border-radius: 6px;
            color: white;
            display: inline-flex;
            font-size: .9rem;
            font-weight: 800;
            height: 36px;
            justify-content: center;
            letter-spacing: .04em;
            min-width: 92px;
            padding: 0 12px;
        }
        .app-copy {
            color: var(--muted);
            font-size: .92rem;
            line-height: 1.25rem;
        }
        .section-title {
            color: var(--ink);
            font-size: 1rem;
            font-weight: 700;
            margin: 1.25rem 0 .35rem;
        }
        .muted { color: var(--muted); font-size: .92rem; }
        div.stDownloadButton > button {
            background: var(--brand);
            border-color: var(--brand);
            color: white;
        }
        div.stDownloadButton > button:hover {
            background: var(--brand-dark);
            border-color: var(--brand-dark);
            color: white;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def construir_excel(df_final: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_final.to_excel(writer, sheet_name="Intereses", index=False)
        ws = writer.sheets["Intereses"]
        widths = {
            "A": 16,
            "B": 14,
            "C": 14,
            "D": 18,
            "E": 16,
            "F": 12,
            "G": 26,
        }
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
        for cell in ws[1]:
            cell.style = "Headline 4"
    return output.getvalue()


def preparar_salida(df: pd.DataFrame, fecha_op: date, fecha_liq: date) -> pd.DataFrame:
    salida = pd.DataFrame(
        {
            "FONDO": df["Portfolio"].map(portfolio_a_fondo),
            "FECHA OP": pd.to_datetime(fecha_op),
            "FECHA LIQ": pd.to_datetime(fecha_liq),
            "CONTRAPARTE": df["Banco"].str.upper(),
            "IMPORTE": df["Intereses"],
            "DIVISA": df["Moneda"],
            "ARCHIVO ORIGEN": df.get("Archivo", ""),
        }
    )
    return salida.sort_values(["FONDO", "DIVISA", "CONTRAPARTE"]).reset_index(drop=True)


st.markdown(
    """
    <div class="app-header">
        <div class="app-mark">INT</div>
        <div class="app-copy">Operacion de intereses<br>Estados de cuenta bancarios</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.title("Procesador de movimientos")
st.markdown(
    '<div class="muted">Carga los estados de cuenta, revisa los intereses detectados y descarga el Excel listo para trabajar.</div>',
    unsafe_allow_html=True,
)

fecha_default = date.today()
col_fecha_op, col_fecha_liq, col_gap = st.columns([1, 1, 2])
with col_fecha_op:
    fecha_op = st.date_input("Fecha OP", value=fecha_default, format="DD/MM/YYYY")
with col_fecha_liq:
    fecha_liq = st.date_input("Fecha LIQ", value=fecha_default + timedelta(days=1), format="DD/MM/YYYY")

st.markdown('<div class="section-title">Archivos</div>', unsafe_allow_html=True)
archivos = st.file_uploader(
    "Sube uno o varios PDF de movimientos",
    type=["pdf"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

if not archivos:
    st.info("Sube los PDFs para generar el resultado.")
    st.stop()

with st.spinner("Leyendo movimientos..."):
    with TemporaryDirectory() as tmp_dir:
        rutas = []
        for archivo in archivos:
            ruta = Path(tmp_dir) / archivo.name
            ruta.write_bytes(archivo.getbuffer())
            rutas.append(ruta)
        df_detectado, errores = procesar_lote_pdfs(rutas)

if errores:
    with st.expander("Avisos de lectura", expanded=False):
        for error in errores:
            st.warning(error)

if df_detectado.empty:
    st.error("No encontré intereses en los PDFs cargados.")
    st.stop()

df_final = preparar_salida(df_detectado, fecha_op, fecha_liq)

total = df_final["IMPORTE"].sum()
monedas = ", ".join(sorted(df_final["DIVISA"].dropna().unique()))
fondos = df_final["FONDO"].nunique()

m1, m2, m3 = st.columns(3)
m1.metric("Registros", f"{len(df_final):,}")
m2.metric("Fondos", f"{fondos:,}")
m3.metric("Total detectado", f"${total:,.2f} {monedas}")

st.markdown('<div class="section-title">Resultado editable</div>', unsafe_allow_html=True)
df_editado = st.data_editor(
    df_final,
    width="stretch",
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "FONDO": st.column_config.TextColumn("FONDO", required=True),
        "FECHA OP": st.column_config.DateColumn("FECHA OP", format="DD/MM/YYYY", required=True),
        "FECHA LIQ": st.column_config.DateColumn("FECHA LIQ", format="DD/MM/YYYY", required=True),
        "CONTRAPARTE": st.column_config.TextColumn("CONTRAPARTE", required=True),
        "IMPORTE": st.column_config.NumberColumn("IMPORTE", format="$ %.2f", required=True),
        "DIVISA": st.column_config.SelectboxColumn("DIVISA", options=["MXN", "USD"], required=True),
        "ARCHIVO ORIGEN": st.column_config.TextColumn("ARCHIVO ORIGEN", disabled=True),
    },
)

excel_bytes = construir_excel(df_editado)
st.download_button(
    "Descargar Excel",
    data=excel_bytes,
    file_name=f"intereses_{fecha_op:%Y%m%d}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    width="stretch",
)
