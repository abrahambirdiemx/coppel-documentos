# Birdie KPI Dashboard · Coppel Compliance

Dashboard de KPIs para el piloto Coppel — revisión documental Manual vs Birdie.
Backend FastAPI + frontend HTML dinámico + conexión opcional a Google Sheets.

---

## Estructura del proyecto

```
birdie-kpi-dashboard/
├── main.py                        ← FastAPI app + cálculo de KPIs
├── requirements.txt
├── render.yaml                    ← Deploy config para Render
├── .env.example                   ← Variables de entorno (copia como .env)
├── templates/
│   └── index.html                 ← Dashboard dinámico (Jinja2 + JS)
├── static/                        ← Assets estáticos (vacío por ahora)
└── google_apps_script/
    └── Code.gs                    ← Script para exponer Google Sheet como API
```

---

## Setup local

```bash
# 1. Clonar / abrir en Claude Code
cd birdie-kpi-dashboard

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Copiar variables de entorno
cp .env.example .env

# 4. Correr el servidor
uvicorn main:app --reload --port 8000

# 5. Abrir en browser
open http://localhost:8000
```

Sin configurar `SHEETS_WEBAPP_URL`, el dashboard carga datos de muestra del piloto 09-10 Abr 2026.

---

## Conexión con Google Sheets

### Paso 1 — Publicar el Apps Script como Web App

1. Abre el Google Sheet **Coppel_KPI_Documentos**
2. **Extensions → Apps Script**
3. Pega el contenido de `google_apps_script/Code.gs` en el editor
4. Guarda (`Ctrl+S`)
5. Click **Deploy → New deployment**
   - Type: **Web App**
   - Execute as: **Me**
   - Who has access: **Anyone** *(o Anyone with Google account)*
6. Click **Deploy** → copia la **Web App URL**

### Paso 2 — Configurar la variable de entorno

En tu `.env` local:
```
SHEETS_WEBAPP_URL=https://script.google.com/macros/s/XXXXXXX/exec
```

En Render (producción): Environment → Add Variable → `SHEETS_WEBAPP_URL`

### Paso 3 — Verificar

```bash
curl http://localhost:8000/api/health
# → {"status":"ok","sheets_configured":true}

curl http://localhost:8000/api/data
# → {"source":"sheets","periodo":"...","birdie":{...},...}
```

---

## Deploy en Render

```bash
# Opción A: desde CLI
render deploy

# Opción B: conectar repo en render.com
# New Web Service → Connect GitHub repo → Auto-deploy en push a main
```

El `render.yaml` ya tiene la configuración correcta. Solo necesitas agregar
`SHEETS_WEBAPP_URL` en el dashboard de Render → Environment.

---

## Endpoints API

| Endpoint      | Descripción                                      |
|---------------|--------------------------------------------------|
| `GET /`       | Dashboard HTML                                   |
| `GET /api/data` | JSON con todos los KPIs y registros            |
| `GET /api/health` | Health check + estado de conexión Sheets    |

### Estructura del JSON `/api/data`

```json
{
  "source": "sheets",          // "sheets" | "sample"
  "periodo": "2026-04-09 — 2026-04-10",
  "total_registros": 16,
  "birdie": {
    "sesiones": 8,
    "bookings": 22,
    "docs": 103,
    "err_docs": 15,
    "err_etiq": 76,
    "avg_exp_hora": 8.54,
    "avg_docs_hora": 37.0,
    "tasa_error_docs": 14.56,
    "tasa_error_total": 88.35
  },
  "manual": { ... },
  "registros": [ ... ],        // Array de 16 bloques con KPIs calculados
  "por_tipo": [ ... ]          // Agregado por tipo de expediente y método
}
```

---

## Próximos pasos sugeridos

- [ ] Agregar autenticación básica al endpoint `/api/data` (API key header)
- [ ] Añadir captura de errores en revisión Manual (cols J/K) para comparación de precisión
- [ ] Agregar tab de semana → semana para evolución temporal
- [ ] Integrar directo con Birdie backend en lugar de Sheets (futura fase)

---

## Stack

- **Backend**: FastAPI + uvicorn
- **Frontend**: HTML/CSS/JS vanilla + Chart.js 4.4
- **Fuente de datos**: Google Sheets via Apps Script Web App
- **Deploy**: Render (render.yaml incluido)
- **Fonts**: Raleway (Google Fonts)
