import os
from datetime import datetime
import duckdb
import pandas as pd
import smtplib
from email.message import EmailMessage

# ============================================================
# 1) Validação dos CSVs
# ============================================================

def validar_csv_pedidos(caminho_pedidos: str):
    if not os.path.exists(caminho_pedidos):
        return False, "Arquivo de pedidos não encontrado."

    try:
        df = duckdb.read_csv(
            caminho_pedidos,
            header=True,
            sep=";",
            auto_detect=True,
            all_varchar=True
        ).df()
    except Exception as e:
        return False, f"Erro ao ler pedidos: {e}"

    if df.shape[1] != 5:
        return False, "Arquivo de pedidos deve ter exatamente 5 colunas."

    return True, "Arquivo de pedidos recebido e validado."


def validar_csv_faturamentos(caminho_faturamentos: str):
    if not os.path.exists(caminho_faturamentos):
        return False, "Arquivo de faturamentos não encontrado."

    try:
        df = duckdb.read_csv(
            caminho_faturamentos,
            header=True,
            sep=";",
            auto_detect=True
        ).df()
    except Exception as e:
        return False, f"Erro ao ler faturamentos: {e}"

    if df.shape[1] != 5:
        return False, "Arquivo de faturamentos deve ter exatamente 5 colunas."

    return True, "Arquivo de faturamentos recebido e validado."


# ============================================================
# 2) Processamento OTIF
# ============================================================

def processar_otif(caminho_pedidos: str, caminho_faturamentos: str):
    try:
        # --------------------------------------------------------
        # Leitura robusta com DuckDB (aceita qualquer encoding)
        # --------------------------------------------------------
        pedidos_raw = duckdb.read_csv(
            caminho_pedidos,
            header=True,
            sep=";",
            auto_detect=True,
            all_varchar=True
        ).df()

        fatur_raw = duckdb.read_csv(
            caminho_faturamentos,
            header=True,
            sep=";",
            auto_detect=True,
            all_varchar=True
        ).df()

        # --------------------------------------------------------
        # Renomeia colunas (ajuste conforme seu layout real)
        # --------------------------------------------------------
        pedidos_raw.columns = ["ordem", "cliente", "data_desejada", "sku", "qtd_pedida"]
        fatur_raw.columns   = ["data_fatur", "cliente", "sku", "qtd_faturada", "ordem_venda"]

        # --------------------------------------------------------
        # Converte datas
        # --------------------------------------------------------
        pedidos_raw["data_desejada"] = pd.to_datetime(
            pedidos_raw["data_desejada"], format="%d/%m/%Y", errors="coerce"
        )
        fatur_raw["data_fatur"] = pd.to_datetime(
            fatur_raw["data_fatur"], format="%d/%m/%Y", errors="coerce"
        )

        # --------------------------------------------------------
        # Junta pedidos x faturamentos
        # --------------------------------------------------------
        ped_fatur = pd.merge(
            pedidos_raw,
            fatur_raw,
            left_on=["ordem", "cliente", "sku"],
            right_on=["ordem_venda", "cliente", "sku"],
            how="left",
            suffixes=("_ped", "_fat")
        )

        # --------------------------------------------------------
        # Cálculo OTIF
        # --------------------------------------------------------
        ped_fatur["atendido"] = ped_fatur["qtd_faturada"].fillna(0)
        ped_fatur["otif_qtd"] = (ped_fatur["atendido"] >= ped_fatur["qtd_pedida"]).astype(int)
        ped_fatur["otif_prazo"] = (
            ped_fatur["data_fatur"] <= ped_fatur["data_desejada"]
        ).astype(int)

        ped_fatur["otif_total"] = (
            (ped_fatur["otif_qtd"] == 1) & (ped_fatur["otif_prazo"] == 1)
        ).astype(int)

        # --------------------------------------------------------
        # Consolidação por cliente
        # --------------------------------------------------------
        consol = ped_fatur.groupby("cliente").agg(
            pedidos=("ordem", "nunique"),
            itens=("sku", "nunique"),
            otif_qtd=("otif_qtd", "mean"),
            otif_prazo=("otif_prazo", "mean"),
            otif_total=("otif_total", "mean"),
        ).reset_index()

        # --------------------------------------------------------
        # Gera Excel
        # --------------------------------------------------------
        pasta_saida = os.path.dirname(caminho_pedidos)
        arquivo_xlsx = os.path.join(
            pasta_saida,
            f"OTIF_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        with pd.ExcelWriter(arquivo_xlsx) as writer:
            consol.to_excel(writer, sheet_name="Consolidado", index=False)
            ped_fatur.to_excel(writer, sheet_name="Detalhes", index=False)

        return arquivo_xlsx

    except Exception as e:
        raise Exception(f"Falha ao processar OTIF: {e}")


# ============================================================
# 3) Envio de e-mail
# ============================================================

def enviar_email_otif(arquivo_xlsx: str, email_destino: str):
    # Ajuste conforme seu servidor SMTP real
    smtp_host = "smtp.seuservidor.com"
    smtp_port = 587
    smtp_user = "usuario@seuservidor.com"
    smtp_pass = "sua_senha"

    msg = EmailMessage()
    msg["Subject"] = "Relatório OTIF"
    msg["From"] = smtp_user
    msg["To"] = email_destino
    msg.set_content("Segue em anexo o relatório OTIF gerado automaticamente.")

    with open(arquivo_xlsx, "rb") as f:
        dados = f.read()
        msg.add_attachment(
            dados,
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=os.path.basename(arquivo_xlsx),
        )

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    return True
