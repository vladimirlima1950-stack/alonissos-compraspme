from fastapi import FastAPI, UploadFile, File
import pandas as pd
import duckdb
import os

# Import do módulo OTIF
from modules.otif import processar_otif

app = FastAPI()

# Diretório onde os arquivos serão armazenados temporariamente
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Variáveis globais para armazenar os caminhos dos arquivos
pedidos_path = None
faturamentos_path = None


@app.get("/")
def home():
    return {"status": "online", "mensagem": "API OTIF funcionando"}


@app.post("/upload_pedidos")
async def upload_pedidos(file: UploadFile = File(...)):
    global pedidos_path

    pedidos_path = os.path.join(UPLOAD_DIR, "pedidos.csv")

    with open(pedidos_path, "wb") as f:
        f.write(await file.read())

    return {"status": "ok", "arquivo": "pedidos.csv"}


@app.post("/upload_faturamentos")
async def upload_faturamentos(file: UploadFile = File(...)):
    global faturamentos_path

    faturamentos_path = os.path.join(UPLOAD_DIR, "faturamentos.csv")

    with open(faturamentos_path, "wb") as f:
        f.write(await file.read())

    return {"status": "ok", "arquivo": "faturamentos.csv"}


@app.get("/processar_otif")
def processar_otif_api():
    global pedidos_path, faturamentos_path

    if not pedidos_path or not faturamentos_path:
        return {"erro": "Envie pedidos e faturamentos antes de processar."}

    # Chama o módulo externo OTIF
    consol = processar_otif(pedidos_path, faturamentos_path)

    return {
        "status": "processado",
        "resultado": consol.to_dict(orient="records")
    }
