from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from app.utils.utils import pattern_date, phrases_to_ignore, partial_phrases_to_ignore

from ..services.statement_processor import process_pdf_file, extract_transactions_partial_from_pdf
import pdftotext
import shutil
import os
import time
import json
import csv
import re

router  = APIRouter()

# [CÓDIGO DE OTROS ENDPOINTS - NO MODIFICAR]
# ...otros endpoints...

@router.post("/extract-transactions-json")
async def extract_transactions_json(
    file: UploadFile = File(...),
    output_format: str = Query("json", description="Formato de salida: ndjson o json", regex="^(ndjson|json)$")
):
    """
    Extrae transacciones de un PDF de estado de cuenta bancario.
    
    Formato esperado del PDF:
    - Línea 1: Concepto/Descripción
    - Línea 2: Fecha (dd-mm) + Montos ($ cargo $ abono $ saldo)
    - Línea 3: Información adicional (códigos, folios, etc.)
    """
    temp_path = f"temp/{file.filename}"
    os.makedirs("temp", exist_ok=True)

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        start_time = time.time()
        results = []

        # Expresiones regulares
        money_re = re.compile(r"\$\s?[\d,]+\.\d{2}")
        date_re = re.compile(r"^\s*\d{2}-\d{2}\b")
        folio_re = re.compile(r"FOLIO[:\s]*[:#\-]?\s*([0-9]+)", re.IGNORECASE)

        with open(temp_path, "rb") as f:
            pdf = pdftotext.PDF(f, physical=True)
            
            # Unificar todas las líneas de todas las páginas
            all_lines = []
            for page in pdf:
                all_lines.extend(page.split("\n"))
            
            # Procesar línea por línea
            i = 0
            while i < len(all_lines):
                line = all_lines[i].strip()
                
                # Ignorar líneas vacías o encabezados
                if not line or any(phrase in line for phrase in partial_phrases_to_ignore):
                    i += 1
                    continue
                
                # Buscar línea con fecha (indica una transacción)
                date_match = date_re.search(line)
                if not date_match:
                    i += 1
                    continue
                
                # === TRANSACCIÓN ENCONTRADA ===
                fecha = date_match.group(0).strip()
                
                # Extraer montos de esta línea
                amounts = [amt.replace(" ", "") for amt in money_re.findall(line)]
                
                # CONCEPTO: revisar línea ANTERIOR
                concepto = None
                if i > 0:
                    prev = all_lines[i-1].strip()
                    if prev and not date_re.search(prev) and not any(ph in prev for ph in partial_phrases_to_ignore):
                        # Si tiene montos, tomar solo la parte antes del $
                        concepto = prev.split('$')[0].strip() if '$' in prev else prev
                
                # Si no hay concepto anterior, buscar en la línea actual (después de fecha)
                if not concepto:
                    after_date = line[date_match.end():].strip()
                    if after_date and '$' in after_date:
                        concepto = after_date.split('$')[0].strip()
                
                # INFORMACIÓN ADICIONAL: revisar líneas SIGUIENTES (folios, códigos)
                folio = None
                next_info = []
                j = i + 1
                while j < len(all_lines) and len(next_info) < 2:
                    nxt = all_lines[j].strip()
                    if not nxt:
                        j += 1
                        continue
                    # Si encontramos otra fecha, detenemos
                    if date_re.search(nxt):
                        break
                    # Si no tiene montos, es información adicional
                    if not money_re.search(nxt):
                        next_info.append(nxt)
                        # Buscar FOLIO
                        fm = folio_re.search(nxt)
                        if fm:
                            folio = fm.group(1)
                    j += 1
                
                # ASIGNAR MONTOS
                cargo = abono = saldo = None
                if len(amounts) == 1:
                    abono = amounts[0]
                elif len(amounts) == 2:
                    # Determinar si es cargo o abono por palabras clave
                    if concepto and any(k in concepto.upper() for k in ["CHEQUE", "PAGADO", "COMPRA", "CARGO"]):
                        cargo, saldo = amounts
                    else:
                        abono, saldo = amounts
                elif len(amounts) >= 3:
                    cargo, abono, saldo = amounts[0], amounts[1], amounts[2]
                
                # Ajuste especial para cheques
                if concepto and "CHEQUE PAGADO" in concepto.upper() and abono and not cargo:
                    cargo = abono
                    abono = None
                
                # RAW LINES para debugging
                raw = []
                if i > 0 and all_lines[i-1].strip():
                    raw.append(all_lines[i-1].strip())
                raw.append(line)
                raw.extend(next_info)
                
                # Agregar transacción
                results.append({
                    "fecha": fecha,
                    "concepto": concepto,
                    "folio": folio,
                    "cargo": cargo,
                    "abono": abono,
                    "saldo": saldo,
                    "raw_lines": raw
                })
                
                i += 1

        # Guardar resultados según formato solicitado
        file_name = temp_path[5:-4].strip().replace(" ", "_")
        if output_format == "json":
            array_path = f"temp/{file_name}_transactions_array.json"
            with open(array_path, "w", encoding="utf-8") as jf:
                json.dump(results, jf, ensure_ascii=False, indent=2)
            return FileResponse(
                array_path,
                filename=f"{file_name}_transactions.json",
                media_type="application/json"
            )
        else:
            ndjson_path = f"temp/{file_name}_transactions.json"
            with open(ndjson_path, "w", encoding="utf-8") as out_f:
                for obj in results:
                    out_f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            return FileResponse(
                ndjson_path,
                filename=f"{file_name}_transactions.json",
                media_type="application/x-ndjson"
            )

    except ValueError as ve:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {ve}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
