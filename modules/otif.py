import os
from datetime import datetime, date
import duckdb
import pandas as pd
import smtplib
from email.message import EmailMessage

# ============================================================
# Função de LOG (console + arquivo, modo append)
# ============================================================

def log(msg):
    print(msg)  # console do Railway

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
# 2) Processamento OTIF — versão fiel ao MySQL + logs resumidos
# ============================================================

def processar_otif(caminho_pedidos: str, caminho_faturamentos: str):
    try:
        # --------------------------------------------------------
        # Separador de execução
        # --------------------------------------------------------
        log("############################################################")
        log(f"# OTIF EXECUTADO EM {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log("############################################################")

        log("Iniciando OTIF...")

        # --------------------------------------------------------
        # Leitura com DuckDB (mantido conforme solicitado)
        # --------------------------------------------------------
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

        # --------------------------------------------------------
        # Renomeia colunas conforme MySQL
        # --------------------------------------------------------
        pedidos.columns = ["ordem", "cliente", "dta_desejada", "sku", "qde_pedida"]
        fatur.columns   = ["dta_efetiva", "cliente", "sku", "qde_fatur", "numero_ordem"]

        # ============================================================
        # FASE 1 — equivalente ao sp1 (limpeza e conversão)
        # ============================================================

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

        # ============================================================
        # FASE 2 — equivalente ao sp2 (junção pedidos + faturamentos)
        # ============================================================

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

        # ============================================================
        # FASE 3 — equivalente ao sp3 (pontuações OTIF)
        # ============================================================

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

        # ============================================================
        # FASE 4 — equivalente ao sp4 (backorder)
        # ============================================================

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

        # ============================================================
        # FASE FINAL — gerar Excel
        # ============================================================

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
# 3) Envio de e-mail
# ============================================================

def enviar_email_otif(arquivo_xlsx: str, email_destino: str):
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
