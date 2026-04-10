"""
Birdie KPI Dashboard — Coppel Compliance
FastAPI backend con conexión a Google Sheets via Apps Script Web App o CSV público
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
import csv
import io
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Birdie KPI Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─── Fuente de datos (set en .env) ────────────────────────────────────────
# Opción A — Apps Script Web App JSON:  SHEETS_WEBAPP_URL=https://script.google.com/...
# Opción B — Sheet publicado como CSV:  SHEETS_CSV_URL=https://docs.google.com/spreadsheets/d/ID/gviz/tq?tqx=out:csv&sheet=...
SHEETS_URL     = os.getenv("SHEETS_WEBAPP_URL", "")
SHEETS_CSV_URL = os.getenv("SHEETS_CSV_URL", "")

# El Sheet tiene 4 filas antes de los headers reales (título, subtítulo, vacía, grupo)
CSV_HEADER_ROW = 4  # índice 0-based de la fila con los encabezados reales

# Mapeo de encabezados CSV → campos internos
# Los headers del Sheet tienen saltos de línea, los normalizamos antes de comparar
CSV_COL = {
    "num":       ["#"],
    "fecha":     ["Fecha"],
    "bloque":    ["Bloque"],
    "revisor":   ["Revisor"],
    "metodo":    ["Método", "Metodo"],
    "tipo":      ["Tipo de expediente"],
    "bookings":  ["Bookings revisados"],
    "docs":      ["Documentos revisados"],
    "etiquetas": ["Etiquetas revisadas"],
    "err_docs":  ["Errores documentos: Error en validacion de reglas",
                  "Errores documentos:Error en validacion de reglas",
                  "Errores documentos"],
    "err_etiq":  ["Errores etiquetas: Error en validacion de reglas",
                  "Errores etiquetas:Error en validacion de reglas",
                  "Errores etiquetas"],
    "tiempo":    ["Tiempo bloque (min)"],
}


def _normalize(s: str) -> str:
    """Elimina saltos de línea y espacios extra para comparación."""
    return " ".join(s.replace("\n", " ").split()).strip()


def _find_col(header_row: list[str], candidates: list[str]) -> str | None:
    norm_map = {_normalize(h): h for h in header_row}
    for c in candidates:
        original = norm_map.get(_normalize(c))
        if original:
            return original
    return None


def parse_csv_to_payload(csv_text: str) -> dict:
    lines = csv_text.splitlines()
    # Saltar filas de título hasta encontrar la fila que empieza con "#"
    header_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("#") or line.strip().startswith('"#"'):
            header_idx = i
            break

    data_csv = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(data_csv))
    headers = reader.fieldnames or []

    col_map = {field: _find_col(headers, candidates) for field, candidates in CSV_COL.items()}

    registros = []
    for row in reader:
        num = row.get(col_map["num"] or "", "").strip()
        fecha = row.get(col_map["fecha"] or "", "").strip()
        metodo = row.get(col_map["metodo"] or "", "").strip()
        if not num or not fecha or not metodo:
            continue

        def flt(field):
            val = row.get(col_map[field] or "", "0").strip().replace(",", ".")
            try:
                return float(val)
            except ValueError:
                return 0.0

        docs = flt("docs")
        tiempo = flt("tiempo")
        bk = flt("bookings")
        err_docs = flt("err_docs")
        err_etiq = flt("err_etiq")

        exp_por_hora  = round(bk / (tiempo / 60), 2) if tiempo > 0 else 0
        docs_por_hora = round(docs / (tiempo / 60), 2) if tiempo > 0 else 0
        tasa_error     = round((err_docs + err_etiq) / docs * 100, 2) if docs > 0 else 0
        tasa_error_docs = round(err_docs / docs * 100, 2) if docs > 0 else 0

        registros.append({
            "num":            float(num) if num.replace(".", "").isdigit() else 0,
            "fecha":          fecha,
            "bloque":         row.get(col_map["bloque"] or "", "").strip(),
            "revisor":        row.get(col_map["revisor"] or "", "").strip(),
            "metodo":         metodo,
            "tipo":           row.get(col_map["tipo"] or "", "").strip(),
            "bookings":       bk,
            "docs":           docs,
            "etiquetas":      flt("etiquetas"),
            "err_docs":       err_docs,
            "err_etiq":       err_etiq,
            "tiempo":         tiempo,
            "exp_por_hora":   exp_por_hora,
            "docs_por_hora":  docs_por_hora,
            "tasa_error":     tasa_error,
            "tasa_error_docs": tasa_error_docs,
        })

    birdie = [r for r in registros if r["metodo"] == "Birdie"]
    manual = [r for r in registros if r["metodo"] == "Manual"]

    def agg(rows):
        if not rows:
            return {}
        total_docs     = sum(r["docs"] for r in rows)
        total_bk       = sum(r["bookings"] for r in rows)
        total_err_docs = sum(r["err_docs"] for r in rows)
        total_err_etiq = sum(r["err_etiq"] for r in rows)
        avg_exp_h  = round(sum(r["exp_por_hora"] for r in rows) / len(rows), 2)
        avg_doc_h  = round(sum(r["docs_por_hora"] for r in rows) / len(rows), 2)
        return {
            "sesiones":         len(rows),
            "bookings":         total_bk,
            "docs":             total_docs,
            "err_docs":         total_err_docs,
            "err_etiq":         total_err_etiq,
            "avg_exp_hora":     avg_exp_h,
            "avg_docs_hora":    avg_doc_h,
            "tasa_error_docs":  round(total_err_docs / total_docs * 100, 2) if total_docs > 0 else 0,
            "tasa_error_total": round((total_err_docs + total_err_etiq) / total_docs * 100, 2) if total_docs > 0 else 0,
        }

    tipos: dict = {}
    for r in registros:
        key = f"{r['tipo']}|{r['metodo']}"
        if key not in tipos:
            tipos[key] = {"tipo": r["tipo"], "metodo": r["metodo"], "docs_hora": [], "exp_hora": []}
        tipos[key]["docs_hora"].append(r["docs_por_hora"])
        tipos[key]["exp_hora"].append(r["exp_por_hora"])

    por_tipo = [
        {
            "tipo":          v["tipo"],
            "metodo":        v["metodo"],
            "avg_docs_hora": round(sum(v["docs_hora"]) / len(v["docs_hora"]), 2),
            "avg_exp_hora":  round(sum(v["exp_hora"])  / len(v["exp_hora"]),  2),
        }
        for v in tipos.values()
    ]

    fechas = sorted(r["fecha"] for r in registros if r["fecha"])
    periodo = f"{fechas[0]} — {fechas[-1]}" if fechas else "—"

    return {
        "source":          "csv",
        "periodo":         periodo,
        "total_registros": len(registros),
        "birdie":          agg(birdie),
        "manual":          agg(manual),
        "registros":       registros,
        "por_tipo":        por_tipo,
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/data")
async def get_data():
    """
    Prioridad: Apps Script JSON → CSV público → datos de muestra
    """
    # Opción A: Apps Script Web App (JSON)
    if SHEETS_URL:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(SHEETS_URL)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            print(f"[WARN] Apps Script fetch failed: {e}")

    # Opción B: CSV público
    if SHEETS_CSV_URL:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(SHEETS_CSV_URL)
                resp.raise_for_status()
                return parse_csv_to_payload(resp.text)
        except Exception as e:
            print(f"[WARN] CSV fetch failed: {e}")

    return get_sample_data()


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "mode": "apps_script" if SHEETS_URL else ("csv" if SHEETS_CSV_URL else "sample"),
    }


def get_sample_data() -> dict:
    """
    Datos de muestra hardcodeados del piloto 09-10 Abr 2026.
    Reemplazados automáticamente cuando SHEETS_WEBAPP_URL está configurado.
    """
    registros = [
        {"num":1,  "fecha":"2026-04-09","bloque":"Mañana","revisor":"LAURA",   "metodo":"Birdie","tipo":"Muebles", "bookings":1,"docs":18,"etiquetas":0, "err_docs":1,"err_etiq":0, "tiempo":20},
        {"num":2,  "fecha":"2026-04-09","bloque":"Mañana","revisor":"LAURA",   "metodo":"Manual","tipo":"Muebles", "bookings":1,"docs":21,"etiquetas":0, "err_docs":0,"err_etiq":0, "tiempo":40},
        {"num":3,  "fecha":"2026-04-09","bloque":"Mañana","revisor":"ERIKA",   "metodo":"Manual","tipo":"Ropa",    "bookings":2,"docs":6, "etiquetas":18,"err_docs":0,"err_etiq":0, "tiempo":25},
        {"num":4,  "fecha":"2026-04-09","bloque":"Mañana","revisor":"ERIKA",   "metodo":"Birdie","tipo":"Ropa",    "bookings":3,"docs":9, "etiquetas":31,"err_docs":5,"err_etiq":20,"tiempo":28},
        {"num":5,  "fecha":"2026-04-09","bloque":"Tarde", "revisor":"LAURA",   "metodo":"Birdie","tipo":"Calzado", "bookings":1,"docs":2, "etiquetas":0, "err_docs":1,"err_etiq":0, "tiempo":5},
        {"num":6,  "fecha":"2026-04-09","bloque":"Tarde", "revisor":"LAURA",   "metodo":"Manual","tipo":"Calzado", "bookings":1,"docs":2, "etiquetas":0, "err_docs":0,"err_etiq":0, "tiempo":10},
        {"num":7,  "fecha":"2026-04-09","bloque":"Mañana","revisor":"FERNANDO","metodo":"Manual","tipo":"Muebles", "bookings":5,"docs":19,"etiquetas":42,"err_docs":0,"err_etiq":0, "tiempo":28.22},
        {"num":8,  "fecha":"2026-04-09","bloque":"Mañana","revisor":"FERNANDO","metodo":"Birdie","tipo":"Muebles", "bookings":5,"docs":24,"etiquetas":42,"err_docs":1,"err_etiq":5, "tiempo":31.21},
        {"num":9,  "fecha":"2026-04-09","bloque":"Tarde", "revisor":"LAURA",   "metodo":"Birdie","tipo":"Muebles", "bookings":1,"docs":4, "etiquetas":0, "err_docs":1,"err_etiq":0, "tiempo":5},
        {"num":10, "fecha":"2026-04-09","bloque":"Tarde", "revisor":"LAURA",   "metodo":"Manual","tipo":"Muebles", "bookings":1,"docs":4, "etiquetas":8, "err_docs":0,"err_etiq":0, "tiempo":20},
        {"num":11, "fecha":"2026-04-09","bloque":"Tarde", "revisor":"ERIKA",   "metodo":"Manual","tipo":"Ropa",    "bookings":2,"docs":6, "etiquetas":8, "err_docs":0,"err_etiq":0, "tiempo":23},
        {"num":12, "fecha":"2026-04-09","bloque":"Tarde", "revisor":"ERIKA",   "metodo":"Birdie","tipo":"Ropa",    "bookings":3,"docs":8, "etiquetas":18,"err_docs":3,"err_etiq":24,"tiempo":25},
        {"num":13, "fecha":"2026-04-09","bloque":"Tarde", "revisor":"VALERIA", "metodo":"Manual","tipo":"Juguetes","bookings":3,"docs":16,"etiquetas":24,"err_docs":0,"err_etiq":0, "tiempo":35.19},
        {"num":14, "fecha":"2026-04-09","bloque":"Tarde", "revisor":"FERNANDO","metodo":"Manual","tipo":"Muebles", "bookings":4,"docs":14,"etiquetas":24,"err_docs":0,"err_etiq":0, "tiempo":26.47},
        {"num":15, "fecha":"2026-04-09","bloque":"Tarde", "revisor":"FERNANDO","metodo":"Birdie","tipo":"Muebles", "bookings":4,"docs":18,"etiquetas":24,"err_docs":1,"err_etiq":2, "tiempo":24.56},
        {"num":16, "fecha":"2026-04-09","bloque":"Tarde", "revisor":"VALERIA", "metodo":"Birdie","tipo":"Juguetes","bookings":4,"docs":20,"etiquetas":25,"err_docs":2,"err_etiq":25,"tiempo":29},
    ]

    # Compute KPIs
    for r in registros:
        d = r["docs"]
        t = r["tiempo"]
        bk = r["bookings"]
        r["exp_por_hora"]  = round(bk / (t / 60), 2) if t > 0 else 0
        r["docs_por_hora"] = round(d / (t / 60), 2)  if t > 0 else 0
        r["tasa_error"]    = round((r["err_docs"] + r["err_etiq"]) / d * 100, 2) if d > 0 else 0
        r["tasa_error_docs"] = round(r["err_docs"] / d * 100, 2) if d > 0 else 0

    birdie = [r for r in registros if r["metodo"] == "Birdie"]
    manual = [r for r in registros if r["metodo"] == "Manual"]

    def agg(rows):
        total_bk   = sum(r["bookings"] for r in rows)
        total_docs = sum(r["docs"] for r in rows)
        total_err_docs = sum(r["err_docs"] for r in rows)
        total_err_etiq = sum(r["err_etiq"] for r in rows)
        avg_exp_h  = round(sum(r["exp_por_hora"] for r in rows) / len(rows), 2)
        avg_doc_h  = round(sum(r["docs_por_hora"] for r in rows) / len(rows), 2)
        tasa_docs  = round(total_err_docs / total_docs * 100, 2) if total_docs > 0 else 0
        tasa_total = round((total_err_docs + total_err_etiq) / total_docs * 100, 2) if total_docs > 0 else 0
        return {
            "sesiones": len(rows),
            "bookings": total_bk,
            "docs": total_docs,
            "err_docs": total_err_docs,
            "err_etiq": total_err_etiq,
            "avg_exp_hora": avg_exp_h,
            "avg_docs_hora": avg_doc_h,
            "tasa_error_docs": tasa_docs,
            "tasa_error_total": tasa_total,
        }

    # Por tipo
    tipos = {}
    for r in registros:
        key = f"{r['tipo']}|{r['metodo']}"
        if key not in tipos:
            tipos[key] = {"tipo": r["tipo"], "metodo": r["metodo"], "docs_hora": [], "exp_hora": []}
        tipos[key]["docs_hora"].append(r["docs_por_hora"])
        tipos[key]["exp_hora"].append(r["exp_por_hora"])

    por_tipo = [
        {
            "tipo": v["tipo"],
            "metodo": v["metodo"],
            "avg_docs_hora": round(sum(v["docs_hora"]) / len(v["docs_hora"]), 2),
            "avg_exp_hora":  round(sum(v["exp_hora"])  / len(v["exp_hora"]),  2),
        }
        for v in tipos.values()
    ]

    return {
        "source": "sample",
        "periodo": "09-10 Abr 2026",
        "total_registros": len(registros),
        "birdie": agg(birdie),
        "manual": agg(manual),
        "registros": registros,
        "por_tipo": por_tipo,
    }
