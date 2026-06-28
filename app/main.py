from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

import pandas as pd
import tempfile
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


@app.post("/generar-pdf")
async def generar_pdf(
    request: Request,
    plaza: str = Form(...),
    cliente: str = Form(...),
    periodo: str = Form(...),
    fecha: str = Form(...),
    folio: str = Form(...),
    observaciones: str = Form(""),
    csv_file: UploadFile = File(...)
):

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(await csv_file.read())
        archivo = tmp.name

    df = None

    for encoding in ["utf-8-sig", "utf-8", "cp1252", "latin1"]:
        try:
            df = pd.read_csv(archivo, sep=";", encoding=encoding)
            break
        except Exception:
            pass

    if df is None:
        return HTMLResponse(
            "<h2>No fue posible leer el archivo SCU200.</h2>",
            status_code=400
        )

    columna_coste = None

    for columna in df.columns:
        nombre = str(columna).lower()

        if "coste" in nombre or "costo" in nombre or "importe" in nombre:
            columna_coste = columna
            break

    if columna_coste is None:
        return HTMLResponse(
            "<h2>No se encontró la columna de Coste / Costo / Importe.</h2>",
            status_code=400
        )

    serie = (
        df[columna_coste]
        .astype(str)
        .str.strip()
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .replace("-", "0")
        .replace("", "0")
    )

    serie_numerica = pd.to_numeric(serie, errors="coerce").fillna(0)

    total = float(serie_numerica.sum())

    html = templates.TemplateResponse(
        request=request,
        name="recibo.html",
        context={
            "plaza": plaza,
            "cliente": cliente,
            "periodo": periodo,
            "fecha": fecha,
            "folio": folio,
            "observaciones": observaciones,
            "total": "${:,.2f}".format(total)
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