from fastapi import FastAPI
from app.api.routes_transacciones import router as transacciones_router # type: ignore
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Execution-Time", "X-Total-Count", "X-Json"],

)

app.include_router(transacciones_router, prefix="/api/v1", tags=["Transacciones"])

#   & 'c:\Users\TheNex\anaconda3\envs\bautcher-match-env\python.exe' 'c:\Users\TheNex\.vscode\extensions\ms-python.debugpy-2025.6.0-win32-x64\bundled\libs\debugpy\launcher' '55071' '--' '-m' 'uvicorn' 'app.app:app' '--reload' 