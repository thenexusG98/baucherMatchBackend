from fastapi import APIRouter, UploadFile, File, HTTPException, Query, BackgroundTasks
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

def cleanup_files(*file_paths):
    """Elimina archivos temporales después de ser procesados"""
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Archivo eliminado: {file_path}")
        except Exception as e:
            print(f"Error al eliminar {file_path}: {e}")

@router.post("/download-pdf")
async def upload_pdf(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
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
        
        # Programar eliminación de archivos temporales
        background_tasks.add_task(cleanup_files, temp_path, movimientos)
        
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
    

@router.post("/download-csv")
async def upload_csv(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):

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

        total_abonos = sum(float(item.get('ABONOS', 0)) for item in data if isinstance(item, dict))
        print(f"Total ABONOS: ${total_abonos}")
        
        # Write CSV
        if isinstance(data, list) and data:
            keys = data[0].keys()
            with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=keys)
                writer.writeheader()
                writer.writerows(data)
        else:
            raise HTTPException(status_code=422, detail="El archivo JSON no contiene datos válidos para CSV.")

        # Programar eliminación de archivos temporales
        background_tasks.add_task(cleanup_files, temp_path, movimientos_json_path, csv_path)

        response = FileResponse(
            csv_path,
            filename=f"{file_name}.csv",
            media_type="text/csv"
        )
        po = json.dumps({"execution_time": execution_time, "total_count": len(data), "income_month": total_abonos})

        response.headers["X-json"] = po
        return response
    
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {ve}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")




@router.post("/extract-partial-json")
async def extract_transactions_json(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
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
            
            # Programar eliminación de archivos temporales
            background_tasks.add_task(cleanup_files, temp_path, array_path)
            
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
            
            # Programar eliminación de archivos temporales
            background_tasks.add_task(cleanup_files, temp_path, ndjson_path)
            
            return FileResponse(
                ndjson_path,
                filename=f"{file_name}_transactions.json",
                media_type="application/x-ndjson"
            )

    except ValueError as ve:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {ve}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
    


@router.post("/extract-partial-csv")
async def extract_transactions_csv(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Extrae transacciones de un PDF de estado de cuenta bancario y retorna un archivo CSV.
    
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
                numero_control = None
                
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
                        # Buscar número de control en la misma línea (formato: 000ITCV21690056)
                        nc_inline = re.search(r"(?:\d{3})?(?:ITCV)?(\d{2}69\d{4})", concepto)
                        if nc_inline:
                            numero_control = nc_inline.group(1)
                            # Limpiar el número de control del concepto
                            concepto = re.sub(r"/?\d{3}?ITCV?\d{2}69\d{4}", "", concepto).strip()
                
                # INFORMACIÓN ADICIONAL: revisar líneas SIGUIENTES (folios, códigos)
                folio = None
                next_info = []
                j = i + 1
                while j < len(all_lines) and len(next_info) < 2:
                    nxt = all_lines[j].strip()
                    
                    # Buscar número de control en las líneas siguientes
                    # Patrón 1: ITCV21690160 (con prefijo ITCV)
                    # Patrón 2: 23690586 (solo dígitos con 69 en medio)
                    if not numero_control:
                        nc = re.search(r"(?:ITCV)?(\d{2}69\d{4})", nxt)
                        if nc:
                            numero_control = nc.group(1)
                    
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
                
                # Agregar transacción (sin raw_lines para CSV)
                results.append({
                    "fecha": fecha,
                    "concepto": concepto,
                    "folio": folio,
                    "cargo": cargo,
                    "abono": abono,
                    "saldo": saldo,
                    "numero_control": numero_control
                })
                
                i += 1

        # Guardar resultados en formato CSV
        file_name = temp_path[5:-4].strip().replace(" ", "_")
        csv_path = f"temp/{file_name}_transactions.csv"
        
        if results:
            keys = results[0].keys()
            with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=keys)
                writer.writeheader()
                writer.writerows(results)
        else:
            raise HTTPException(status_code=422, detail="No se encontraron transacciones en el PDF.")
        
        execution_time = time.time() - start_time
        
        # Programar eliminación de archivos temporales
        background_tasks.add_task(cleanup_files, temp_path, csv_path)
        
        response = FileResponse(
                csv_path,
                filename=f"{file_name}_transactions.csv",
                media_type="text/csv"
            )
        response.headers["X-Execution-Time"] = str(execution_time)
        return response

    except ValueError as ve:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {ve}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
