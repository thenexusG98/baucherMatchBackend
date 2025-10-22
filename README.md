# 🏦 Baucher Match Backend

API REST desarrollada con FastAPI para la extracción y procesamiento automatizado de transacciones bancarias desde estados de cuenta en formato PDF.

## 📋 Descripción

Este proyecto permite procesar estados de cuenta bancarios (específicamente de BBVA Bancomer) en formato PDF y extraer las transacciones de manera estructurada. La API es capaz de identificar y clasificar automáticamente depósitos, cargos, transferencias SPEI y otros movimientos bancarios, extrayendo información relevante como:

- Fechas de operación y liquidación
- Conceptos y descripciones
- Montos (cargos y abonos)
- Números de control y folios
- Saldos de operación y liquidación

## ✨ Características

- **Extracción inteligente**: Procesa PDFs utilizando OCR físico para mayor precisión
- **Múltiples formatos de salida**: JSON, CSV y NDJSON
- **Detección automática**: Identifica tipos de transacciones (depósitos, SPEI, cheques, etc.)
- **Números de control**: Extrae automáticamente números de control de depósitos
- **Cálculos automáticos**: Suma total de abonos mensuales
- **Metadatos de rendimiento**: Incluye tiempo de ejecución en las respuestas
- **CORS habilitado**: Configurado para trabajar con aplicaciones frontend
- **Filtrado inteligente**: Ignora encabezados y texto no relevante del PDF

## 🚀 Tecnologías

- **FastAPI**: Framework web moderno y de alto rendimiento
- **pdftotext**: Extracción de texto de PDFs con modo físico
- **Python 3.10+**: Lenguaje de programación
- **Uvicorn**: Servidor ASGI de alto rendimiento
- **Pydantic**: Validación de datos

## 📁 Estructura del Proyecto

```
baucherMatchBackend-main/
├── app/
│   ├── __init__.py
│   ├── app.py                      # Aplicación principal FastAPI
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes_transacciones.py # Endpoints de la API
│   ├── services/
│   │   ├── __init__.py
│   │   └── statement_processor.py  # Lógica de procesamiento de PDFs
│   └── utils/
│       ├── __init__.py
│       ├── functions.py            # Funciones auxiliares de extracción
│       └── utils.py                # Constantes y patrones
├── temp/                           # Directorio temporal para archivos procesados
├── requeriments.txt                # Dependencias del proyecto
└── README.md
```

## 🔧 Instalación

### Prerrequisitos

- Python 3.10 o superior
- pip (gestor de paquetes de Python)
- poppler-utils (para pdftotext)

#### Instalación de poppler (requerido para pdftotext):

**macOS:**
```bash
brew install poppler
```

**Ubuntu/Debian:**
```bash
sudo apt-get install build-essential libpoppler-cpp-dev pkg-config python3-dev
```

**Windows:**
- Descarga poppler desde [poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases/)
- Agrega el directorio `bin` al PATH del sistema

### Pasos de instalación

1. **Clonar el repositorio**
```bash
git clone https://github.com/thenexusG98/baucherMatchBackend.git
cd baucherMatchBackend-main
```

2. **Crear entorno virtual (recomendado)**
```bash
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. **Instalar dependencias**
```bash
pip install -r requeriments.txt
```

## 🎯 Uso

### Iniciar el servidor

```bash
uvicorn app.app:app --reload
```

El servidor estará disponible en `http://localhost:8000`

### Documentación interactiva

Una vez iniciado el servidor, accede a la documentación automática:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 📡 Endpoints de la API

### 1. Descargar JSON

**POST** `/api/v1/download-pdf`

Procesa un PDF y retorna un archivo JSON con las transacciones estructuradas.

**Request:**
- Tipo: `multipart/form-data`
- Campo: `file` (archivo PDF)

**Response:**
```json
{
  "file": "archivo.json",
  "execution_time": 1.234
}
```

**Estructura del JSON de transacciones:**
```json
[
  {
    "FECHA_OPER": "01/ENE",
    "FECHA_LIQ": "01/ENE",
    "COD_DESCRIPCION": "DEPOSITO EFECTIVO SUCURSAL",
    "CARGOS": 0,
    "ABONOS": 1000.00,
    "OPERACION": 1000.00,
    "LIQUIDACION": 15000.00,
    "NUMERO_CONTROL": "23690156"
  }
]
```

---

### 2. Descargar CSV

**POST** `/api/v1/download-csv`

Procesa un PDF y retorna un archivo CSV con las transacciones.

**Request:**
- Tipo: `multipart/form-data`
- Campo: `file` (archivo PDF)

**Response:**
- Archivo CSV descargable
- Headers personalizados:
  - `X-json`: Metadatos en formato JSON
    ```json
    {
      "execution_time": 1.234,
      "total_count": 45,
      "income_month": 125000.50
    }
    ```

---

### 3. Extracción Parcial JSON

**POST** `/api/v1/extract-partial-json?output_format=json`

Extrae transacciones utilizando un algoritmo de análisis línea por línea más detallado.

**Parámetros:**
- `output_format`: `json` o `ndjson` (default: `json`)

**Request:**
- Tipo: `multipart/form-data`
- Campo: `file` (archivo PDF)

**Response (JSON):**
```json
[
  {
    "fecha": "01-01",
    "concepto": "DEPOSITO EFECTIVO",
    "folio": "12345",
    "cargo": null,
    "abono": "$1,000.00",
    "saldo": "$15,000.00",
    "raw_lines": ["...", "..."]
  }
]
```

---

### 4. Extracción Parcial CSV

**POST** `/api/v1/extract-partial-csv`

Similar a extract-partial-json pero retorna un archivo CSV. Incluye extracción automática de números de control.

**Request:**
- Tipo: `multipart/form-data`
- Campo: `file` (archivo PDF)

**Response:**
- Archivo CSV con columnas:
  - `fecha`
  - `concepto`
  - `folio`
  - `cargo`
  - `abono`
  - `saldo`
  - `numero_control`

**Headers:**
- `X-Execution-Time`: Tiempo de procesamiento en segundos

---

## 🔍 Algoritmo de Procesamiento

### Método 1: Procesamiento Estructurado (download-pdf/csv)

1. **Extracción de texto**: Usa `pdftotext` en modo físico
2. **Filtrado**: Elimina encabezados, pies de página y texto irrelevante
3. **Detección de transacciones**: Busca líneas con patrón de fecha (`dd/MMM`)
4. **Agrupación de líneas**: Concatena líneas relacionadas a una misma transacción
5. **Extracción de campos**: Usa expresiones regulares para extraer:
   - Fechas de operación y liquidación
   - Montos (cargos, abonos, operación, liquidación)
   - Números de control (para depósitos y SPEI)
   - Descripción completa de la transacción

### Método 2: Análisis Línea por Línea (extract-partial-json/csv)

1. **Lectura completa**: Lee todas las páginas del PDF
2. **Análisis contextual**:
   - **Línea actual**: Contiene fecha y montos
   - **Línea anterior**: Contiene el concepto
   - **Líneas siguientes**: Contienen folios y códigos adicionales
3. **Clasificación automática**: Identifica tipo de transacción (cargo/abono)
4. **Extracción de números de control**: Detecta patrones como `ITCV21690056` o `23690586`

## 🎨 Patrones Reconocidos

El sistema reconoce automáticamente los siguientes tipos de transacciones:

- ✅ **Depósitos en efectivo** → Extrae número de control
- ✅ **Transferencias SPEI recibidas** → Extrae número de control
- ✅ **Pagos de cuenta**
- ✅ **Cheques pagados**
- ✅ **Cargos generales**
- ✅ **Comisiones bancarias**

### Números de Control

Los números de control se extraen automáticamente para:
- Depósitos efectivo en sucursal (patrón: `##69####`)
- Transferencias SPEI recibidas (patrón: `##69####`)
- Se marca como `"NA"` cuando no aplica

## ⚙️ Configuración

### CORS

El servidor está configurado para aceptar peticiones desde:
- `http://localhost:1420` (aplicación frontend)

Para modificar los orígenes permitidos, edita `app/app.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420"],  # Modifica aquí
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Directorio Temporal

Los archivos procesados se guardan temporalmente en `/temp`. Este directorio se crea automáticamente si no existe.

## 🧪 Pruebas

Puedes probar la API usando curl:

```bash
# Ejemplo: Procesar PDF y obtener JSON
curl -X POST "http://localhost:8000/api/v1/download-pdf" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/ruta/a/tu/estado_cuenta.pdf"

# Ejemplo: Procesar PDF y obtener CSV
curl -X POST "http://localhost:8000/api/v1/download-csv" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/ruta/a/tu/estado_cuenta.pdf" \
  --output transacciones.csv
```

O usando la interfaz Swagger en `http://localhost:8000/docs`

## 📊 Formato de Estados de Cuenta Soportados

El sistema está optimizado para procesar estados de cuenta de **BBVA Bancomer** con el siguiente formato:

```
FECHA    CONCEPTO                           CARGOS    ABONOS    SALDO
01/ENE   DEPOSITO EFECTIVO SUCURSAL                   1000.00   15000.00
01/ENE                                                
         ITCV23690156
```

## 🛠️ Dependencias Principales

| Paquete | Versión | Propósito |
|---------|---------|-----------|
| fastapi | 0.115.12 | Framework web |
| uvicorn | 0.34.0 | Servidor ASGI |
| pdftotext | 3.0.0 | Extracción de texto de PDFs |
| pydantic | 2.11.3 | Validación de datos |
| python-multipart | 0.0.20 | Manejo de archivos multipart |

## 🐛 Manejo de Errores

La API retorna los siguientes códigos de estado HTTP:

- `200 OK`: Procesamiento exitoso
- `400 Bad Request`: Archivo no es PDF
- `422 Unprocessable Entity`: Error al procesar el contenido del PDF
- `500 Internal Server Error`: Error interno del servidor

## 🚧 Limitaciones Conocidas

- Optimizado específicamente para estados de cuenta de BBVA Bancomer
- Requiere que el PDF contenga texto seleccionable (no imágenes escaneadas)
- Los patrones de fecha deben estar en formato `dd/MMM` (ej: `01/ENE`)

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📝 Licencia

Este proyecto es de código abierto y está disponible bajo la licencia que especifiques.

## 👨‍💻 Autor

**thenexusG98**
- GitHub: [@thenexusG98](https://github.com/thenexusG98)

## 📧 Contacto

Para preguntas, sugerencias o reportar problemas, por favor abre un issue en el repositorio de GitHub.

---

⭐ Si este proyecto te fue útil, considera darle una estrella en GitHub!
