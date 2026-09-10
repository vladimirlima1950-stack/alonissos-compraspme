import os
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse

# Importação das funções do módulo de processamento
from modules.aval_fornec import (
    validar_csv_pedidos,
    validar_csv_entregas,
    validar_csv_leadtime,
    processar_compraspme,
    enviar_email_relatorio
)

app = FastAPI(title="API ComprasPME")

# Diretório de uploads (declarado no topo, igual ao OTIF)
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Variáveis globais para rastrear o caminho dos arquivos enviados
pedidos_path = None
entregas_path = None
leadtime_path = None

def converter_para_utf8(caminho_arquivo: str):
    """Lê o arquivo de entrada (tentando UTF-8 e Latin-1) e sobrescreve em UTF-8."""
    try:
        with open(caminho_arquivo, "rb") as f:
            conteudo = f.read()
        try:
            texto = conteudo.decode("utf-8")
        except UnicodeDecodeError:
            texto = conteudo.decode("latin-1")
        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            f.write(texto)
        return True, "Arquivo convertido para UTF8."
    except Exception as e:
        return False, f"Erro ao converter para UTF8: {str(e)}"

@app.get("/")
def home():
    """Rota de verificação de status da API."""
    return {"status": "online", "mensagem": "API ComprasPME funcionando"}

@app.post("/upload_pedidos")
async def upload_pedidos(file: UploadFile = File(...)):
    """Upload e validação do arquivo de pedidos."""
    global pedidos_path
    try:
        pedidos_path = os.path.join(UPLOAD_DIR, "pedidos.csv")
        contents = await file.read()
        if len(contents) < 10:
            return JSONResponse(
                status_code=400,
                content={"status": "erro", "mensagem": "Arquivo de pedidos vazio ou muito pequeno."}
            )
        with open(pedidos_path, "wb") as f:
            f.write(contents)
        ok_conv, msg_conv = converter_para_utf8(pedidos_path)
        if not ok_conv:
            return JSONResponse(status_code=400, content={"status": "erro", "mensagem": msg_conv})
        ok, msg = validar_csv_pedidos(pedidos_path)
        if not ok:
            return JSONResponse(status_code=400, content={"status": "erro", "mensagem": msg})
        return {"status": "ok", "arquivo": "pedidos.csv", "mensagem": "Arquivo de pedidos recebido e validado."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "erro", "mensagem": str(e)})

@app.post("/upload_entregas")
async def upload_entregas(file: UploadFile = File(...)):
    """Upload e validação do arquivo de entregas."""
    global entregas_path
    try:
        entregas_path = os.path.join(UPLOAD_DIR, "entregas.csv")
        contents = await file.read()
        if len(contents) < 10:
            return JSONResponse(
                status_code=400,
                content={"status": "erro", "mensagem": "Arquivo de entregas vazio ou muito pequeno."}
            )
        with open(entregas_path, "wb") as f:
            f.write(contents)
        ok_conv, msg_conv = converter_para_utf8(entregas_path)
        if not ok_conv:
            return JSONResponse(status_code=400, content={"status": "erro", "mensagem": msg_conv})
        ok, msg = validar_csv_entregas(entregas_path)
        if not ok:
            return JSONResponse(status_code=400, content={"status": "erro", "mensagem": msg})
        return {"status": "ok", "arquivo": "entregas.csv", "mensagem": "Arquivo de entregas recebido e validado."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "erro", "mensagem": str(e)})

@app.post("/upload_leadtime")
async def upload_leadtime(file: UploadFile = File(...)):
    """Upload e validação do arquivo de leadtime."""
    global leadtime_path
    try:
        leadtime_path = os.path.join(UPLOAD_DIR, "leadtime.csv")
        contents = await file.read()
        if len(contents) < 10:
            return JSONResponse(
                status_code=400,
                content={"status": "erro", "mensagem": "Arquivo de leadtime vazio ou muito pequeno."}
            )
        with open(leadtime_path, "wb") as f:
            f.write(contents)
        ok_conv, msg_conv = converter_para_utf8(leadtime_path)
        if not ok_conv:
            return JSONResponse(status_code=400, content={"status": "erro", "mensagem": msg_conv})
        ok, msg = validar_csv_leadtime(leadtime_path)
        if not ok:
            return JSONResponse(status_code=400, content={"status": "erro", "mensagem": msg})
        return {"status": "ok", "arquivo": "leadtime.csv", "mensagem": "Arquivo de leadtime recebido e validado."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "erro", "mensagem": str(e)})

@app.get("/processar_compraspme")
def processar_compraspme_api(email: str):
    """Executa o pipeline no DuckDB e envia os relatórios por e-mail."""
    global pedidos_path, entregas_path, leadtime_path
    if not pedidos_path or not entregas_path or not leadtime_path:
        return JSONResponse(
            status_code=400,
            content={"status": "erro", "mensagem": "Envie pedidos, entregas e leadtime antes de processar."}
        )
    try:
        pasta_saida = processar_compraspme(pedidos_path, entregas_path, leadtime_path)
        enviar_email_relatorio(pasta_saida, email)
        return {
            "status": "processado",
            "mensagem": "Processamento concluído e enviado por e-mail.",
            "diretorio_saida": str(pasta_saida)
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "erro", "mensagem": str(e)})