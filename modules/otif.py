import os
import base64
from datetime import datetime, date
import duckdb
import pandas as pd
import requests

# ============================================================
# Função de LOG (console + arquivo)
# ============================================================

def log(msg):
    print(msg)

    log_path = os.path.join("uploads", "log.txt")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception as e:
        print(f"Falha ao escrever log: {e}")


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
            auto_detect=True,
            all_varchar=True
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
        log("############################################################")
        log(f"# OTIF EXECUTADO EM {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log("############################################################")

        log("Iniciando OTIF...")

        pedidos = duckdb.read_csv(
            caminho_pedidos,
            header=True,
            sep=";",
            auto_detect=True,
            all_varchar=True
        ).df()

        fatur = duckdb.read_csv(
            caminho_faturamentos,
            header=True,
            sep=";",
            auto_detect=True,
            all_varchar=True
        ).df()

        log(f"Pedidos lidos: {len(pedidos)} linhas")
        log(f"Faturamentos lidos: {len(fatur)} linhas")

        pedidos.columns = ["ordem", "cliente", "dta_desejada", "sku", "qde_pedida"]
        fatur.columns   = ["dta_efetiva", "cliente", "sku", "qde_fatur", "numero_ordem"]

        log("Convertendo quantidades...")

        pedidos["qde_pedida"] = pd.to_numeric(pedidos["qde_pedida"], errors="coerce").fillna(0)
        pedidos.loc[pedidos["qde_pedida"] < 0, "qde_pedida"] = 0

        fatur["qde_fatur"] = pd.to_numeric(fatur["qde_fatur"], errors="coerce").fillna(0)
        fatur.loc[fatur["qde_fatur"] < 0, "qde_fatur"] = 0

        log("Convertendo datas...")

        pedidos["dta_desejada_amer"] = pd.to_datetime(
            pedidos["dta_desejada"], errors="coerce", dayfirst=True
        )

        ano_ref = date.today().year
        mes_ref = date.today().month - 2
        if mes_ref <= 0:
            mes_ref += 12
            ano_ref -= 1
        data_padrao = date(ano_ref, mes_ref, 1)

        fatur["dta_efetiva"] = fatur["dta_efetiva"].replace("", None)
        fatur["dta_efetiva_amer"] = pd.to_datetime(
            fatur["dta_efetiva"], errors="coerce", dayfirst=True
        )
        fatur["dta_efetiva_amer"] = fatur["dta_efetiva_amer"].fillna(data_padrao)

        log("Executando resumo de faturamento...")

        resumo = fatur.groupby(["numero_ordem", "sku"]).agg(
            max_data=("dta_efetiva_amer", "max"),
            tot_fatur=("qde_fatur", "sum")
        ).reset_index()

        log("Executando merge pedidos + faturamentos...")

        ped_fatur = pd.merge(
            pedidos,
            fatur,
            left_on=["ordem", "sku"],
            right_on=["numero_ordem", "sku"],
            how="left"
        )

        ped_fatur = pd.merge(
            ped_fatur,
            resumo,
            left_on=["ordem", "sku"],
            right_on=["numero_ordem", "sku"],
            how="left"
        )

        log(f"Linhas após merge: {len(ped_fatur)}")

        log("Calculando pontuações OTIF...")

        ped_fatur["max_data"] = ped_fatur["max_data"].fillna(pd.NaT)
        ped_fatur["tot_fatur"] = ped_fatur["tot_fatur"].fillna(0)

        ped_fatur["pontua_data"] = (
            ped_fatur["max_data"] <= ped_fatur["dta_desejada_amer"]
        ).astype(int)

        ped_fatur["pontua_qde"] = (
            ped_fatur["tot_fatur"] >= ped_fatur["qde_pedida"]
        ).astype(int)

        ped_fatur["pontua_total"] = (
            (ped_fatur["pontua_data"] + ped_fatur["pontua_qde"]) == 2
        ).astype(int)

        ped_fatur["ano"] = ped_fatur["dta_desejada_amer"].dt.year
        ped_fatur["mes"] = ped_fatur["dta_desejada_amer"].dt.month

        consol_fase2 = ped_fatur.groupby(["ano", "mes"]).agg(
            total_linhas=("sku", "count"),
            linhas_atendidas=("pontua_total", "sum")
        ).reset_index()

        consol_fase2["nivel_servico_perct"] = (
            consol_fase2["linhas_atendidas"] / consol_fase2["total_linhas"] * 100
        )

        log("Calculando backorder...")

        fase3 = ped_fatur[ped_fatur["tot_fatur"] < ped_fatur["qde_pedida"]].copy()
        fase3["dias_pendentes"] = (
            pd.Timestamp(date.today()) - fase3["dta_desejada_amer"]
        ).dt.days

        fase4 = pd.DataFrame({
            "total_ordens": [fase3["ordem"].nunique()],
            "total_dias": [fase3["dias_pendentes"].sum()]
        })
        fase4["idade_backorder"] = (
            fase4["total_dias"] / fase4["total_ordens"]
            if fase4["total_ordens"][0] > 0 else 0
        )

        log("Gerando Excel...")

        pasta_saida = os.path.dirname(caminho_pedidos)
        arquivo_xlsx = os.path.join(
            pasta_saida,
            f"OTIF_COMPLETO_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        with pd.ExcelWriter(arquivo_xlsx) as writer:
            ped_fatur.to_excel(writer, sheet_name="Ped_Fatur", index=False)
            consol_fase2.to_excel(writer, sheet_name="Nivel_Servico", index=False)
            fase3.to_excel(writer, sheet_name="Backorder_Detalhes", index=False)
            fase4.to_excel(writer, sheet_name="Backorder_Resumo", index=False)

        log(f"Excel gerado: {arquivo_xlsx}")
        log("Processamento OTIF concluído.")

        return arquivo_xlsx

    except Exception as e:
        log(f"Erro interno: {e}")
        raise Exception(f"Falha ao processar OTIF: {e}")


# ============================================================
# 3) Envio de e-mail via RESEND
# ============================================================

def enviar_email_otif(arquivo_xlsx: str, email_destino: str):
    log(f"Enviando e-mail OTIF para {email_destino} via Resend...")

    RESEND_API_KEY = os.getenv("RESEND_API_KEY")
    if not RESEND_API_KEY:
        log("ERRO: RESEND_API_KEY não configurada no Railway.")
        return False

    with open(arquivo_xlsx, "rb") as f:
        arquivo_bytes = f.read()

    arquivo_base64 = base64.b64encode(arquivo_bytes).decode("utf-8")

    payload = {
        "from": "MUPE Consultoria <noreply@mupeconsult.com>",
        "to": email_destino,
        "subject": "Relatório OTIF",
        "html": "<p>Segue em anexo o relatório OTIF gerado automaticamente.</p>",
        "attachments": [
            {
                "filename": os.path.basename(arquivo_xlsx),
                "content": arquivo_base64,
                "type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
        ]
    }

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        },
        json=payload
    )

    if 200 <= response.status_code < 300:
        log("E-mail enviado com sucesso via Resend.")
        return True
    else:
        log(f"Erro ao enviar e-mail via Resend: {response.text}")
        return False
