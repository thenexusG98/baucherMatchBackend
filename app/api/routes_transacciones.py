from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from ..services.statement_processor import process_pdf_file

import shutil
import os
import time

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
        print(movimientos)
        #return {
            #"filename": file.filename,
            #"status": "procesado correctamente",
            #"time": f"{execution_time:.2f}"
            #"movimientos": movimientos
            #}
        return FileResponse(
            movimientos,
            filename=f"{file_name}.json",
            media_type="application/json"
        )
    
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=f"Error al procesar el PDF: {ve}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")