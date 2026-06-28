# App de intereses

App en Streamlit para leer PDFs de movimientos, detectar intereses por fondo y descargar el resultado en Excel.

## Abrir la app

```bash
streamlit run app.py
```

## Flujo

1. Selecciona la Fecha OP y Fecha LIQ con los calendarios.
2. Sube uno o varios PDFs.
3. Revisa o ajusta el resultado en la tabla editable.
4. Descarga el Excel.

## Columnas del Excel

- FONDO
- FECHA OP
- FECHA LIQ
- CONTRAPARTE
- IMPORTE
- DIVISA
- ARCHIVO ORIGEN
