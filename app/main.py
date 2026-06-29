from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
import pandas as pd
import tempfile
import base64
from weasyprint import HTML

app = FastAPI(title="Lumiere Billing Portal")
templates = Jinja2Templates(directory="/app/app/templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="form.html",
        context={"title": "Lumiere Billing Portal"}
    )


def leer_csv_scu200(archivo):
    for encoding in ["utf-8-sig", "utf-8", "cp1252", "latin1"]:
        for sep in [";", ",", "\t"]:
            try:
                df = pd.read_csv(archivo, sep=sep, encoding=encoding)
                if len(df.columns) >= 2:
                    return df
            except Exception:
                pass
    return None


def detectar_columna_costo(df):
    palabras = ["coste", "costo", "cost", "importe", "amount", "total", "billing"]
    for columna in df.columns:
        nombre = str(columna).lower().strip()
        if any(p in nombre for p in palabras):
            return columna
    return None


def detectar_cliente(df):
    try:
        primera_columna = df.columns[0]
        valores = df[primera_columna].astype(str).str.strip()
        valores = valores[(valores != "") & (valores.str.lower() != "nan") & (valores != "-")]
        if len(valores) > 0:
            return valores.iloc[0]
    except Exception:
        pass
    return ""


def calcular_total(df, columna_costo):
    serie = (
        df[columna_costo]
        .astype(str)
        .str.strip()
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .replace("-", "0")
        .replace("", "0")
        .replace("nan", "0")
    )
    return float(pd.to_numeric(serie, errors="coerce").fillna(0).sum())


async def convertir_logo_a_base64(archivo_logo):
    if archivo_logo is None or archivo_logo.filename == "":
        return ""

    nombre = archivo_logo.filename.lower()

    extensiones = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".svg": "image/svg+xml"
    }

    mime = None
    for ext, tipo in extensiones.items():
        if nombre.endswith(ext):
            mime = tipo
            break

    if mime is None:
        return ""

    contenido = await archivo_logo.read()
    encoded = base64.b64encode(contenido).decode("utf-8")

    return f"data:{mime};base64,{encoded}"


@app.post("/generar-pdf")
async def generar_pdf(
    request: Request,
    plaza: str = Form(""),
    cliente: str = Form(""),
    periodo: str = Form(""),
    fecha: str = Form(""),
    folio: str = Form("REC-000001"),
    observaciones: str = Form(""),
    csv_file: UploadFile = File(...),
    logo_plaza: UploadFile = File(None),
    logo_cliente: UploadFile = File(None)
):

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(await csv_file.read())
        archivo = tmp.name

    df = leer_csv_scu200(archivo)

    if df is None:
        return HTMLResponse("<h2>No fue posible leer el archivo SCU200.</h2>", status_code=400)

    columna_costo = detectar_columna_costo(df)

    if columna_costo is None:
        columnas = ", ".join([str(c) for c in df.columns])
        return HTMLResponse(
            f"<h2>No se encontró la columna de costo.</h2><pre>{columnas}</pre>",
            status_code=400
        )

    cliente_detectado = detectar_cliente(df)
    cliente_final = cliente.strip() if cliente.strip() else cliente_detectado

    total = calcular_total(df, columna_costo)

    logo_plaza_base64 = await convertir_logo_a_base64(logo_plaza)
    logo_cliente_base64 = await convertir_logo_a_base64(logo_cliente)

    html = templates.TemplateResponse(
        request=request,
        name="recibo.html",
        context={
            "plaza": plaza,
            "cliente": cliente_final,
            "periodo": periodo,
            "fecha": fecha,
            "folio": folio,
            "observaciones": observaciones,
            "total": "${:,.2f}".format(total),
            "logo_plaza": logo_plaza_base64,
            "logo_cliente": logo_cliente_base64,
            "columna_costo": str(columna_costo)
        }
    )

    pdf = HTML(string=html.body.decode()).write_pdf()

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=recibo_{folio}.pdf"
        }
    )