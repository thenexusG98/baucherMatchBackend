from app.utils.utils import pattern_date, phrases_to_ignore
from app.utils.functions import clean_total_movements_line, extract_fields
 
import re 
import json
import pdftotext

data = []

def extract_transactions_from_pdf(pdf_name):
    analyze = False
    data = []
    analyze = False
    data_line = []

    with open(pdf_name, "rb") as file:
        pdf = pdftotext.PDF(file, physical=True)
        for page in pdf:
            lines = page.split("\n")

            for line in lines:
                line = line.strip() 

                if any(phrase in line for phrase in phrases_to_ignore):
                    continue

                if "FECHA" in line:
                    analyze = True
                    continue

                if "TOTAL MOVIMIENTOS ABONOS" in line:
                    analyze = True
                    movements = clean_total_movements_line(line)
                    break

                if analyze:
                    line = line.replace(',', '') 
                    if re.match(pattern_date, line):  
                        if data_line: 
                            data.append(data_line)
                        data_line = line  
                    else:
                        if data_line: 
                            data_line += " " + line

    if data_line:
        data.append(data_line)

    last_record = data[-1]
    match_last_ref = re.search(r"Ref\. \**\d+", last_record)
    if match_last_ref:
        text_cleaned = last_record[:match_last_ref.end()]
        data[-1] = text_cleaned
    else:
        text_cleaned = last_record

    return data

def process_pdf_file(pdf_path):
    file_name = pdf_path[8:-4].strip().replace(" ", "_")
    print(f"Processing PDF file: {pdf_path[8:-4]}")
    json_result = []

    extracted_data = extract_transactions_from_pdf(pdf_path)
    
    for data in extracted_data:
        result = extract_fields(data)
        json_result.append(result)

    json_file_path = f"{file_name}.json"
    with open(json_file_path, "w", encoding="utf-8") as json_file:
        json.dump(json_result, json_file, ensure_ascii=False, indent=4)

    return json_file_path
