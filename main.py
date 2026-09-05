from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import os

from modules.otif import (
    processar_otif,
    validar_csv_pedidos,
    validar_csv_faturamentos,
    enviar_email_otif
)


# ============================================================
# Função necessária: converter arquivo para UTF‑8
# ============================================================
def converter_para_utf8(caminho_arquivo):
    try:
        # Lê o arquivo em binário
        with open(caminho_arquivo, "rb") as f:
            conteudo = f.read()

        # Tenta decodificar como UTF‑8
        try:
            texto = conteudo.decode("utf-8")
        except UnicodeDecodeError:
            # Se falhar, tenta Latin‑1
            texto = conteudo.decode("latin-1")

        # Regrava o arquivo em UTF‑8
        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            f.write(texto)

        return True, "Arquivo convertido para UTF‑8."

    except Exception as e:
        return False, f"Erro ao converter para UTF‑8: {str(e)}"


# ============================================================
# Configuração da API
# ============================================================
app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

pedidos_path = None
faturamentos_path = None


@app.get("/")
def home():
    return {"status": "online", "mensagem": "API OTIF funcionando"}


# ============================================================
# Upload de pedidos
# ============================================================
@app.post("/upload_pedidos")
async def upload_pedidos(file: UploadFile = File(...)):
    global pedidos_path

    try:
        pedidos_path = os.path.join(UPLOAD_DIR, "pedidos.csv")

        contents = await file.read()
        if len(contents) < 10:
            return JSONResponse(
                status_code=400,
                content={"status": "erro", "mensagem": "Arquivo de pedidos está vazio ou muito pequeno."}
            )

        # 1) SALVA O ARQUIVO
        with open(pedidos_path, "wb") as f:
            f.write(contents)

        # 2) CONVERTE PARA UTF‑8
        ok_conv, msg_conv = converter_para_utf8(pedidos_path)
        if not ok_conv:
            return JSONResponse(
                status_code=400,
                content={"status": "erro", "mensagem": msg_conv}
            )

        # 3) VALIDA O ARQUIVO
        ok, msg = validar_csv_pedidos(pedidos_path)
        if not ok:
            return JSONResponse(
                status_code=400,
                content={"status": "erro", "mensagem": msg}
            )

        return {"status": "ok", "arquivo": "pedidos.csv", "mensagem": "Arquivo de pedidos recebido e validado."}

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "erro", "mensagem": f"Falha ao receber pedidos: {str(e)}"}
        )


# ============================================================
# Upload de faturamentos
# ============================================================
@app.post("/upload_faturamentos")
async def upload_faturamentos(file: UploadFile = File(...)):
    global faturamentos_path

    try:
        faturamentos_path = os.path.join(UPLOAD_DIR, "faturamentos.csv")

        contents = await file.read()
        if len(contents) < 10:
            return JSONResponse(
                status_code=400,
                content={"status": "erro", "mensagem": "Arquivo de faturamentos está vazio ou muito pequeno."}
            )

        # 1) SALVA O ARQUIVO
        with open(faturamentos_path, "wb") as f:
            f.write(contents)

        # 2) CONVERTE PARA UTF‑8
        ok_conv, msg_conv = converter_para_utf8(faturamentos_path)
        if not ok_conv:
            return JSONResponse(
                status_code=400,
                content={"status": "erro", "mensagem": msg_conv}
            )

        # 3) VALIDA O ARQUIVO
        ok, msg = validar_csv_faturamentos(faturamentos_path)
        if not ok:
            return JSONResponse(
                status_code=400,
                content={"status": "erro", "mensagem": msg}
            )

        return {"status": "ok", "arquivo": "faturamentos.csv", "mensagem": "Arquivo de faturamentos recebido e validado."}

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "erro", "mensagem": f"Falha ao receber faturamentos: {str(e)}"}
        )


# ============================================================
# Processamento OTIF
# ============================================================
@app.get("/processar_otif")
def processar_otif_api():
    global pedidos_path, faturamentos_path

    if not pedidos_path or not faturamentos_path:
        return JSONResponse(
            status_code=400,
            content={"status": "erro", "mensagem": "Envie pedidos e faturamentos antes de processar."}
        )

    try:
        consol, detalhes, arquivo = processar_otif(pedidos_path, faturamentos_path)

        destinatario = os.getenv("CLIENT_EMAIL")
        enviar_email_otif(destinatario, consol, detalhes, arquivo)

        return {
            "status": "processado",
            "mensagem": "Processamento concluído e enviado por e-mail.",
            "arquivo_xlsx": arquivo
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "erro", "mensagem": f"Falha ao processar OTIF: {str(e)}"}
        )
