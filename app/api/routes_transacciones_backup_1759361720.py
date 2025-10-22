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

@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    temp_path = f"temp/{file.filename}"
    os.makedirs("temp", exist_ok=True)

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")
    
    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        start_time = time.time()
        movimientos = process_pdf_file(temp_path)
        execution_time = time.time() - start_time
        
        file_name = temp_path[8:-4].strip().replace(" ", "_")
        
        return {
            "file": FileResponse(
                movimientos,
                filename=f"{file_name}.json",
                media_type="application/json"
            ),
            "execution_time": execution_time
        }
    
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {ve}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
    

@router.post("/download-partial-pdf")
async def upload_partial_pdf(file: UploadFile = File(...)):
    temp_path = f"temp/{file.filename}"

    os.makedirs("temp", exist_ok=True)

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")
    
    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        start_time = time.time()
        lineas_txt = []
        with open(temp_path, "rb") as f:
            pdf = pdftotext.PDF(f, physical=True)
            for i, page in enumerate(pdf):
                lines = page.split("\n")
                deposito_line = ""
                folio_line = ""
                fecha_line = ""
                for linea in lines:
                # Excluir líneas que parecen fechas con hora al inicio del PDF
                    if i == 0 and linea.strip().startswith(tuple("0123456789")) and " - " in linea and ":" in linea:
                        continue
                    # Ignorar líneas que contienen frases a excluir
                    if any(phrase in linea for phrase in partial_phrases_to_ignore):
                        continue
                    # Ignorar líneas que contienen una fecha completa (formato dd/mm/yyyy)
                    if re.search(r"\b\d{2}/\d{2}/\d{4}\b", linea):
                        continue

                    #lineas_txt.append(linea)
                    date_re = re.compile(r"\b\d{2}-\d{2}\b")
                    if date_re.search(linea):
                        fecha_line = linea
                        lineas_txt.append(fecha_line)
                        continue
                
                    if "DEPOSITO" in linea:
                        deposito_line = linea
                        #lineas_txt.append(deposito_line)
                        continue
                    if "FOLIO" in linea:
                        folio_line = linea
                        continue

                    #if deposito_line and ("FOLIO:" not in linea):
                        #lineas_txt.append(deposito_line)
                     #   deposito_line = None
                    
                    #print(fecha_line)
                    #print(type(deposito_line))
                    #lineas_txt.append(deposito_line)
                    
        # Guardar resultado como TXT
        file_name = temp_path[8:-4].strip().replace(" ", "_")
        txt_path = f"temp/{file_name}_lines.txt"

        with open(txt_path, "w", encoding="utf-8") as txt_file:
            for linea in lineas_txt:
                txt_file.write(linea + "\n")

        return FileResponse(
            txt_path,
            filename=f"{file_name}_lines.txt",
            media_type="text/plain"
        )
    
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {ve}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
    

@router.post("/download-csv")
async def upload_csv(file: UploadFile = File(...)):

    temp_path = f"temp/{file.filename}"
    os.makedirs("temp", exist_ok=True)

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")
    
    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        start_time = time.time()
        movimientos_json_path = process_pdf_file(temp_path)
        execution_time = time.time() - start_time

        # Read JSON data
        with open(movimientos_json_path, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)

        # Prepare CSV path
        file_name = temp_path[8:-4].strip().replace(" ", "_")
        csv_path = f"temp/{file_name}.csv"

        # Write CSV
        if isinstance(data, list) and data:
            keys = data[0].keys()
            with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=keys)
                writer.writeheader()
                writer.writerows(data)
        else:
            raise HTTPException(status_code=422, detail="El archivo JSON no contiene datos válidos para CSV.")

        return {
            "file": FileResponse(
                csv_path,
                filename=f"{file_name}.csv",
                media_type="text/csv"
            ),
            "execution_time": execution_time
        }
    
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {ve}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
    

@router.post("/extract-transactions-json")
async def extract_transactions_json(
    file: UploadFile = File(...),
    output_format: str = Query("ndjson", description="Formato de salida: ndjson o json", regex="^(ndjson|json)$")
):
    temp_path = f"temp/{file.filename}"
    os.makedirs("temp", exist_ok=True)

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        start_time = time.time()
        results = []

        money_re = re.compile(r"\$\s?[\d,]+\.\d{2}")
        # Fecha anclada al inicio de línea para evitar coincidencias dentro del concepto
        date_re = re.compile(r"^\s*\d{2}-\d{2}\b")
        folio_re = re.compile(r"FOLIO[:\s]*[:#\-]?\s*([0-9]+)", re.IGNORECASE)

        with open(temp_path, "rb") as f:
            pdf = pdftotext.PDF(f, physical=True)
            
            # Procesar todas las páginas como un flujo continuo para no perder transacciones entre páginas
            all_lines = []
            for page in pdf:
                page_lines = page.split("\n")
                all_lines.extend(page_lines)
            
            in_tx = False
            current_date = None
            concept_buffer = []
            skip_until = -1
            
            for idx, linea in enumerate(all_lines):
                # si ya fue consumida por lookahead de una transacción previa
                if idx <= skip_until:
                    continue
                if not linea or any(phrase in linea for phrase in partial_phrases_to_ignore):
                    continue

                # Detectar fecha (inicio de transacción)
                date_match = date_re.search(linea)
                if date_match:
                    new_date = date_match.group(0).strip()
                    # Caso: fecha duplicada consecutiva (no había concepto todavía) -> solo actualizar
                    if in_tx and not concept_buffer:
                        current_date = new_date
                        rest = linea[date_match.end():].strip()
                        if rest and not date_re.match(rest):
                            concept_buffer.append(rest)
                        continue
                    # Caso: fecha dentro de un concepto previo mal detectada (si la línea tiene texto antes de la fecha) -> ignorar como nueva transacción
                    prefix = linea[:date_match.start()].strip()
                    if prefix:
                        # tratar esta fecha incrustada como parte del concepto existente si estamos en una transacción
                        if in_tx:
                            concept_buffer.append(linea.strip())
                            continue
                    # Nueva transacción normal
                    in_tx = True
                    current_date = new_date
                    concept_buffer = []
                    rest = linea[date_match.end():].strip()
                    if rest and not date_re.match(rest):
                        concept_buffer.append(rest)
                    continue
                        
                if not in_tx:
                    continue

                # Si línea contiene monto(s), cerrar transacción
                amounts = money_re.findall(linea)
                # buscar montos en siguientes 3 líneas (ampliado para capturar más casos)
                for j in range(1, 4):
                    if idx + j < len(all_lines):
                        line_ahead = all_lines[idx + j]
                        # detener si encontramos una nueva fecha (evitar mezclar transacciones)
                        if date_re.search(line_ahead):
                            break
                        amounts += money_re.findall(line_ahead)
                            
                if amounts:
                    # Capturamos posibles líneas adicionales (concepto / folio) que vienen DESPUÉS de los montos
                    lookahead_extra = []
                    la_idx = idx + 1
                    lookahead_limit = 0
                    while la_idx < len(all_lines) and lookahead_limit < 3:
                        la_line = all_lines[la_idx].strip()
                        if not la_line:
                            la_idx += 1
                            continue
                        # si aparece una nueva fecha, terminamos el lookahead (inicio siguiente transacción)
                        if date_re.search(la_line):
                            break
                        # si la línea tiene montos nuevos, asumimos que pertenece a otra transacción
                        if money_re.search(la_line):
                            break
                        # si parece encabezado/ruido, se ignora
                        if any(phrase in la_line for phrase in partial_phrases_to_ignore):
                            la_idx += 1
                            continue
                        lookahead_extra.append(la_line)
                        lookahead_limit += 1
                        la_idx += 1
                    
                    # Normalizar montos (quitar espacios)
                    amounts = [a.replace(" ", "") for a in amounts]

                    # Si no tenemos concepto acumulado, intentar mirar hacia atrás más líneas
                    if not concept_buffer:
                        back_candidates = []
                        for back in range(1, 4):  # ampliado a 3 líneas hacia atrás
                            bidx = idx - back

                            if bidx < 0:
                                break
                            prev_line = all_lines[bidx].strip()
                            # detener si encontramos una fecha (inicio de otra transacción)
                            if date_re.search(prev_line):
                                break
                            if (not prev_line or any(ph in prev_line for ph in partial_phrases_to_ignore)
                                or money_re.search(prev_line)):
                                continue
                            # insertar al frente (recorremos hacia atrás)
                            back_candidates.insert(0, prev_line)
                            

                        if back_candidates:
                            concept_buffer.extend(back_candidates)

                    # Normalizar montos: extraer TODOS los montos únicos desde las líneas capturadas
                    all_raw_lines = concept_buffer + [linea] + lookahead_extra
                    all_amounts_found = []
                    seen_amounts = set()
                    
                    for raw_ln in all_raw_lines:
                        found = money_re.findall(raw_ln)
                        for amt in found:
                            amt_clean = amt.replace(" ", "").strip()
                            if amt_clean not in seen_amounts:
                                seen_amounts.add(amt_clean)
                                all_amounts_found.append(amt_clean)
                    
                    # Usar los montos encontrados en orden
                    amounts = all_amounts_found if all_amounts_found else amounts

                    cargo = abono = saldo = None
                    if len(amounts) == 1:
                        abono = amounts[0]
                    elif len(amounts) == 2:
                        # Clasificación heurística por palabras clave
                        lowered_join = " ".join(all_raw_lines).lower()
                        debit_keywords = ["cheque", "pagado", "compra", "retiro", "cargo", "transferencia emit"]
                        credit_keywords = ["deposito", "depósito", "abono", "transferencia recibida"]
                        is_debit = any(k in lowered_join for k in debit_keywords)
                        is_credit = any(k in lowered_join for k in credit_keywords)
                        if is_debit and not is_credit:
                            cargo, saldo = amounts[0], amounts[1]
                        elif is_credit and not is_debit:
                            abono, saldo = amounts[0], amounts[1]
                        else:
                            # fallback original (asumir abono, saldo)
                            abono, saldo = amounts[0], amounts[1]
                    elif len(amounts) >= 3:
                        # Típicamente: cargo, abono, saldo (tomar primeros 3)
                        cargo, abono, saldo = amounts[0], amounts[1], amounts[2]

                    # Construir concepto: priorizar líneas completas con descripción detallada
                    # Primero, identificar la mejor línea de concepto desde todas las disponibles
                    all_concept_sources = concept_buffer + [linea] + lookahead_extra
                    
                    # Filtrar líneas que son puramente montos o fechas
                    clean_sources = []
                    for src in all_concept_sources:
                        src_clean = src.strip()
                        if not src_clean:
                            continue
                        # Extraer parte antes del primer monto (si existe)
                        before_money = src_clean.split('$')[0].strip() if '$' in src_clean else src_clean
                        if before_money and not date_re.search(before_money):
                            clean_sources.append(before_money)
                    
                    # Selección por prioridad de patrones de concepto
                    selected_concept = None
                    
                    # Prioridad 1: Líneas con patrones completos (DEPOSITO EN EFECTIVO/código)
                    for src in clean_sources:
                        if re.search(r'DEPOSITO EN EFECTIVO/\d+', src.upper()):
                            selected_concept = src
                            break
                    
                    # Prioridad 2: CHEQUE PAGADO NO./número
                    if not selected_concept:
                        for src in clean_sources:
                            if re.search(r'CHEQUE PAGADO.+/\d+', src.upper()):
                                selected_concept = src
                                break
                    
                    # Prioridad 3: TRASPASO ENTRE CUENTAS
                    if not selected_concept:
                        for src in clean_sources:
                            if 'TRASPASO ENTRE CUENTAS' in src.upper():
                                selected_concept = src
                                break
                    
                    # Prioridad 4: Línea más larga que no sea "DEPOSITO EFECTIVO PRACTIC" corto
                    if not selected_concept:
                        candidates = [s for s in clean_sources if len(s) > 20 and 'DEPOSITO EFECTIVO PRACTIC' not in s.upper()]
                        if candidates:
                            selected_concept = max(candidates, key=len)
                    
                    # Fallback: la línea más larga disponible
                    if not selected_concept and clean_sources:
                        selected_concept = max(clean_sources, key=len)
                    
                    concepto = selected_concept or None

                    # Post-procesar concepto
                    if concepto and "CHEQUE PAGADO" in concepto.upper():
                        # Para cheques, el monto es cargo (débito)
                        if abono and not cargo:
                            cargo = abono
                            abono = None

                    # Búsqueda de folio en todas las líneas capturadas
                    search_area = " ".join(all_raw_lines)
                    folio = None
                    folio_match = folio_re.search(search_area)
                    if folio_match:
                        folio = folio_match.group(1)

                    # Raw lines sin duplicados
                    raw_lines_unique = []
                    seen_raw = set()
                    for rl in all_raw_lines:
                        rl_stripped = rl.strip()
                        if rl_stripped and rl_stripped not in seen_raw:
                            seen_raw.add(rl_stripped)
                            raw_lines_unique.append(rl_stripped)
                    
                    # Fallback de concepto desde raw_lines si quedó vacío
                    if not concepto and raw_lines_unique:
                        fallback_parts = []
                        for rl in raw_lines_unique:
                            cleaned = money_re.sub('', rl).strip()
                            cleaned = re.sub(r'\s{2,}', ' ', cleaned)
                            if cleaned and not date_re.search(cleaned):
                                fallback_parts.append(cleaned)
                        if fallback_parts:
                            concepto = max(fallback_parts, key=len)  # tomar la más descriptiva
                    
                    tx = {
                        "fecha": current_date,
                        "concepto": concepto,
                        "folio": folio,
                        "cargo": cargo,
                        "abono": abono,
                        "saldo": saldo,
                        "raw_lines": raw_lines_unique
                    }
                    results.append(tx)

                    # actualizamos índice a saltar si absorbimos líneas extra
                    if lookahead_extra:
                        skip_until = la_idx - 1

                    # reset estado para siguiente transacción
                    in_tx = False
                    current_date = None
                    concept_buffer = []
                    continue

                # si no se encontró monto, acumular línea en concepto (puede contener ITCV, folio, etc.)
                concept_buffer.append(linea.strip())
            
            # Cerrar transacción pendiente al final del documento si existe
            if in_tx and concept_buffer:
                # Buscar montos en las últimas líneas del buffer
                pending_amounts = []
                for cb_line in concept_buffer:
                    pending_amounts.extend(money_re.findall(cb_line))
                
                if pending_amounts:
                    # Eliminar duplicados
                    pending_amounts = list(dict.fromkeys([a.replace(" ", "").strip() for a in pending_amounts]))
                    
                    # Extraer concepto sin montos
                    pending_concept_parts = []
                    for cb_line in concept_buffer:
                        cleaned = cb_line.split('$')[0].strip() if '$' in cb_line else cb_line.strip()
                        if cleaned and not date_re.search(cleaned):
                            pending_concept_parts.append(cleaned)
                    
                    pending_concept = max(pending_concept_parts, key=len) if pending_concept_parts else None
                    
                    # Asignar montos
                    p_cargo = p_abono = p_saldo = None
                    if len(pending_amounts) == 1:
                        p_abono = pending_amounts[0]
                    elif len(pending_amounts) == 2:
                        p_abono, p_saldo = pending_amounts[0], pending_amounts[1]
                    elif len(pending_amounts) >= 3:
                        p_cargo, p_abono, p_saldo = pending_amounts[0], pending_amounts[1], pending_amounts[2]
                    
                    # Buscar folio
                    p_search = " ".join(concept_buffer)
                    p_folio = None
                    p_folio_match = folio_re.search(p_search)
                    if p_folio_match:
                        p_folio = p_folio_match.group(1)
                    
                    results.append({
                        "fecha": current_date,
                        "concepto": pending_concept,
                        "folio": p_folio,
                        "cargo": p_cargo,
                        "abono": p_abono,
                        "saldo": p_saldo,
                        "raw_lines": concept_buffer
                    })

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