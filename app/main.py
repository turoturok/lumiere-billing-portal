from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import pandas as pd
import tempfile
from weasyprint import HTML

app = FastAPI(title="Lumiere Billing Portal")

templates = Jinja2Templates(directory="/app/app/templates")
app.mount("/static", StaticFiles(directory="/app/app/static"), name="static")


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


@app.post("/generar-pdf")
async def generar_pdf(
    request: Request,
    plaza: str = Form("Plaza Regia"),
    cliente: str = Form(""),
    periodo: str = Form(""),
    fecha: str = Form(""),
    folio: str = Form("REC-000001"),
    observaciones: str = Form(""),
    csv_file: UploadFile = File(...)
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

    html = templates.TemplateResponse(
        request=request,
        name="recibo.html",
        context={
            "plaza": "Plaza Regia",
            "cliente": cliente_final,
            "periodo": periodo,
            "fecha": fecha,
            "folio": folio,
            "observaciones": observaciones,
            "total": "${:,.2f}".format(total),
            "columna_costo": str(columna_costo),
            "logo_plaza": "/app/app/static/img/plaza-regia.png"
        }
    )

    pdf = HTML(string=html.body.decode(), base_url="/").write_pdf()

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=recibo_{folio}.pdf"
        }
    )