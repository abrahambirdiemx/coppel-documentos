/**
 * Google Apps Script — Birdie KPI Dashboard · Coppel Compliance
 * 
 * INSTRUCCIONES DE DEPLOY:
 * 1. Abre el Google Sheet del KPI Tracker
 * 2. Extensions → Apps Script
 * 3. Pega este código en Code.gs
 * 4. Deploy → New deployment → Web App
 *    - Execute as: Me
 *    - Who has access: Anyone  (o "Anyone with Google account" si quieres más control)
 * 5. Copia la Web App URL y pégala en tu .env como SHEETS_WEBAPP_URL
 */

// ─── Configuración ────────────────────────────────────────────────────────
const SHEET_NAME = "📋 Registro Diario";
const HEADER_ROW = 5;   // Fila donde están los encabezados de columna
const DATA_START = 6;   // Primera fila de datos reales

// Índices de columna (1-based, como en el Sheet)
const COL = {
  NUM:         1,   // A - #
  FECHA:       2,   // B - Fecha
  BLOQUE:      3,   // C - Bloque
  REVISOR:     4,   // D - Revisor
  METODO:      5,   // E - Método
  TIPO:        6,   // F - Tipo de expediente
  BOOKINGS:    7,   // G - Bookings revisados
  DOCS:        8,   // H - Documentos revisados
  ETIQUETAS:   9,   // I - Etiquetas revisadas
  ERR_DOCS:   10,   // J - Errores documentos
  ERR_ETIQ:   11,   // K - Errores etiquetas
  OBSERV:     12,   // L - Observaciones
  TIEMPO:     13,   // M - Tiempo bloque (min)
  TASA_ERR:   17,   // Q - Tasa de error (%)
};

// ─── doGet: endpoint principal ────────────────────────────────────────────
function doGet(e) {
  const data = buildPayload();
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

// ─── Build payload ────────────────────────────────────────────────────────
function buildPayload() {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  const lastRow = sheet.getLastRow();

  const registros = [];

  for (let row = DATA_START; row <= lastRow; row++) {
    const getCell = (col) => sheet.getRange(row, col).getValue();

    const num    = getCell(COL.NUM);
    const fecha  = getCell(COL.FECHA);
    const metodo = getCell(COL.METODO);
    const docs   = getCell(COL.DOCS);
    const tiempo = getCell(COL.TIEMPO);
    const bk     = getCell(COL.BOOKINGS);

    // Skip rows without required identifiers
    if (!num || !fecha || !metodo) continue;
    // Skip rows with no numeric data at all (filas incompletas)
    const docsCheck  = parseFloat(docs)   || 0;
    const bkCheck    = parseFloat(bk)     || 0;
    const tiempoCheck = parseFloat(tiempo) || 0;
    if (docsCheck === 0 && bkCheck === 0 && tiempoCheck === 0) continue;

    const errDocs = parseFloat(getCell(COL.ERR_DOCS)) || 0;
    const errEtiq = parseFloat(getCell(COL.ERR_ETIQ)) || 0;
    const docsNum = parseFloat(docs) || 0;
    const tiempoNum = parseFloat(tiempo) || 0;
    const bkNum = parseFloat(bk) || 0;

    const expPorHora  = tiempoNum > 0 ? Math.round((bkNum / (tiempoNum / 60)) * 100) / 100 : 0;
    const docsPorHora = tiempoNum > 0 ? Math.round((docsNum / (tiempoNum / 60)) * 100) / 100 : 0;
    const tasaErr     = docsNum > 0   ? Math.round(((errDocs) / docsNum * 100) * 100) / 100 : 0;

    // Format fecha as YYYY-MM-DD string
    let fechaStr = "";
    if (fecha instanceof Date) {
      fechaStr = Utilities.formatDate(fecha, Session.getScriptTimeZone(), "yyyy-MM-dd");
    } else {
      fechaStr = String(fecha);
    }

    registros.push({
      num:           parseFloat(num),
      fecha:         fechaStr,
      bloque:        String(getCell(COL.BLOQUE)),
      revisor:       String(getCell(COL.REVISOR)),
      metodo:        String(metodo),
      tipo:          String(getCell(COL.TIPO)),
      bookings:      bkNum,
      docs:          docsNum,
      etiquetas:     parseFloat(getCell(COL.ETIQUETAS)) || 0,
      err_docs:      errDocs,
      err_etiq:      errEtiq,
      tiempo:        tiempoNum,
      exp_por_hora:  expPorHora,
      docs_por_hora: docsPorHora,
      tasa_error:    Math.round(((errDocs + errEtiq) / (docsNum || 1)) * 10000) / 100,
      tasa_error_docs: tasaErr,
    });
  }

  // ── Aggregate helpers ──────────────────────────────────────────────────
  function agg(rows) {
    if (!rows.length) return {};
    const totalDocs    = rows.reduce((s, r) => s + r.docs, 0);
    const totalEtiq    = rows.reduce((s, r) => s + r.etiquetas, 0);
    const totalBk      = rows.reduce((s, r) => s + r.bookings, 0);
    const totalErrDocs = rows.reduce((s, r) => s + r.err_docs, 0);
    const totalErrEtiq = rows.reduce((s, r) => s + r.err_etiq, 0);
    const avgExpH  = round2(rows.reduce((s, r) => s + r.exp_por_hora, 0)  / rows.length);
    const avgDocH  = round2(rows.reduce((s, r) => s + r.docs_por_hora, 0) / rows.length);
    return {
      sesiones:          rows.length,
      bookings:          totalBk,
      docs:              totalDocs,
      etiquetas:         totalEtiq,
      err_docs:          totalErrDocs,
      err_etiq:          totalErrEtiq,
      avg_exp_hora:      avgExpH,
      avg_docs_hora:     avgDocH,
      tasa_error_docs:   totalDocs > 0 ? round2(totalErrDocs / totalDocs * 100) : 0,
      tasa_error_etiq:   totalEtiq > 0 ? round2(totalErrEtiq / totalEtiq * 100) : 0,
      tasa_error_total:  totalDocs > 0 ? round2((totalErrDocs + totalErrEtiq) / totalDocs * 100) : 0,
    };
  }

  function round2(n) { return Math.round(n * 100) / 100; }

  const birdie = registros.filter(r => r.metodo === "Birdie");
  const manual = registros.filter(r => r.metodo === "Manual");

  // ── Por tipo ───────────────────────────────────────────────────────────
  const tipoMap = {};
  for (const r of registros) {
    const key = `${r.tipo}|${r.metodo}`;
    if (!tipoMap[key]) tipoMap[key] = { tipo: r.tipo, metodo: r.metodo, expH: [], docH: [] };
    tipoMap[key].expH.push(r.exp_por_hora);
    tipoMap[key].docH.push(r.docs_por_hora);
  }
  const porTipo = Object.values(tipoMap).map(v => ({
    tipo:          v.tipo,
    metodo:        v.metodo,
    avg_exp_hora:  round2(v.expH.reduce((a, b) => a + b, 0) / v.expH.length),
    avg_docs_hora: round2(v.docH.reduce((a, b) => a + b, 0) / v.docH.length),
  }));

  // ── Periodo ────────────────────────────────────────────────────────────
  const fechas = registros.map(r => r.fecha).filter(Boolean).sort();
  const periodo = fechas.length
    ? `${fechas[0]} — ${fechas[fechas.length - 1]}`
    : "—";

  return {
    source:          "sheets",
    periodo:         periodo,
    total_registros: registros.length,
    birdie:          agg(birdie),
    manual:          agg(manual),
    registros:       registros,
    por_tipo:        porTipo,
    timestamp:       new Date().toISOString(),
  };
}
