import re

def clean_total_movements_line(line):
    """
    Elimina 'TOTAL IMPORTE ABONOS' junto con su monto y 'TOTAL MOVIMIENTOS ABONOS' de la línea,
    dejando solo el número de movimientos.
    """
    # Expresión regular para eliminar 'TOTAL IMPORTE ABONOS' junto con su monto
    pattern_delete = r'TOTAL IMPORTE ABONOS\s+\d{1,3}(?:,\d{3})*\.\d{2}\s+'
    line = re.sub(pattern_delete, '', line)

    # Eliminar 'TOTAL MOVIMIENTOS ABONOS'
    pattern_movements = r'TOTAL MOVIMIENTOS ABONOS'
    line = re.sub(pattern_movements, '', line)
    
    return line.strip()

def extract_fields(text):
    # Extraer fechas
    match_dates = re.findall(r"\d{2}/[A-Z]{3}", text)
    date_oper = match_dates[0] if len(match_dates) > 0 else None
    date_liq = match_dates[1] if len(match_dates) > 1 else None

    # Extraer amounts numéricos
    amounts = re.findall(r"\d+(?:\.\d{2})", text.replace(",", ""))
    amounts_float = list(map(float, amounts))

    # Buscar la posición del primer número decimal para cortar la descripción
    first_number = re.search(r"\d+(?:\.\d{2})", text.replace(",", ""))
    if first_number:
        description = text[:first_number.start()].strip()
        rest = text[first_number.end():].strip()
        description += " " + rest
    else:
        description = text.strip()

    # Eliminar todos los amounts de la descripción
    for monto in amounts:
        description = re.sub(rf"\b{re.escape(monto)}\b", "", description)

    # Limpiar espacios múltiples
    description = re.sub(r"\s{2,}", " ", description).strip()
    header = "OPER LIQ COD. DESCRIPCIÓN REFERENCIA CARGOS ABONOS OPERACIÓN LIQUIDACIÓN"
    description = description.replace(header, "")
    
    charges = abonos = operation = liquidation = 0
    control_number = ""
    
    # Asignar amounts según si es depósito o no
    if "DEPOSITO E" in description.upper():
        #Encuentra el numero de control y lo agrega en json
        match_control_number = re.search(r"(\d{2})69(\d{4})", description)
        if match_control_number:
          resultado = match_control_number.group(1) + "69" + match_control_number.group(2)
          control_number = resultado
        else:
          control_number = "NA"
            
        if len(amounts_float) == 1:
            abonos = amounts_float[0]
        elif len(amounts_float) == 2:
            abonos, operation = amounts_float
        elif len(amounts_float) == 3:
            abonos, operation, liquidation = amounts_float
    elif "PAGO CUENTA" in description.upper():
        control_number = "NA"
        if len(amounts_float) == 1:
            abonos = amounts_float[0]
        elif len(amounts_float) == 2:
            abonos, operation = amounts_float
        elif len(amounts_float) == 3:
            abonos, operation, liquidation = amounts_float
    elif "SPEI RECIBIDO" in description.upper():
        match_control_number = re.search(r"(\d{2})69(\d{4})", description)
        if match_control_number:
          resultado = match_control_number.group(1) + "69" + match_control_number.group(2)
          control_number = resultado
        else:
          control_number = "NA"

        if len(amounts_float) == 1:
            abonos = amounts_float[0]
        elif len(amounts_float) == 2:
            abonos, operation = amounts_float
        elif len(amounts_float) == 3:
            abonos, operation, liquidation = amounts_float
    else:
        control_number = "NA"
        
        if len(amounts_float) == 1:
            charges = amounts_float[0]
        elif len(amounts_float) == 2:
            charges, operation = amounts_float
            liquidation = operation
        elif len(amounts_float) == 3:
            charges, operation, liquidation = amounts_float

    return {
        "FECHA_OPER": date_oper if date_oper else None,
        "FECHA_LIQ": date_liq if date_liq else None,
        "COD_DESCRIPCION": description,
        "CARGOS": charges,
        "ABONOS": abonos,
        "OPERACION": operation,
        "LIQUIDACION": liquidation,
        "NUMERO_CONTROL": control_number
    }