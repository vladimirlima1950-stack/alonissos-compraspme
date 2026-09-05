import pandas as pd
import duckdb
import resend
import os


# ---------- CARREGAMENTO CSV ----------

def carregar_csv_duckdb(path):
    con = duckdb.connect()
    df = con.execute(
        f"""
        SELECT * FROM read_csv_auto(
            '{path}',
            SAMPLE_SIZE=-1,
            ALL_VARCHAR=TRUE
        )
        """
    ).df()
    con.close()
    return df


# ---------- VALIDAÇÃO DOS CSV ----------

def validar_csv_pedidos(path):
    df = carregar_csv_duckdb(path)

    if df.shape[1] != 5:
        return False, f"Arquivo de pedidos deve ter exatamente 5 colunas. Encontradas: {df.shape[1]}."

    df.columns = ["ordem_raw", "cliente_raw", "dta_desejada_raw", "sku_raw", "qde_pedida_raw"]

    if not df["dta_desejada_raw"].str.contains("/").all():
        return False, "A coluna de data desejada (3ª coluna) deve estar no formato DD/MM/AAAA."

    return True, "Arquivo de pedidos válido."


def validar_csv_faturamentos(path):
    df = carregar_csv_duckdb(path)

    if df.shape[1] != 5:
        return False, f"Arquivo de faturamentos deve ter exatamente 5 colunas. Encontradas: {df.shape[1]}."

    df.columns = ["dta_efetiva_raw", "cliente_raw", "sku_raw", "qde_fatur_raw", "numero_ordem_raw"]

    if not df["dta_efetiva_raw"].str.contains("/").all():
        return False, "A coluna de data de faturamento (1ª coluna) deve estar no formato DD/MM/AAAA."

    return True, "Arquivo de faturamentos válido."


# ---------- PREPARAÇÃO DOS DADOS ----------

def preparar_pedidos(df):
    df.columns = ["ordem_raw", "cliente_raw", "dta_desejada_raw", "sku_raw", "qde_pedida_raw"]

    df["ordem"] = df["ordem_raw"].str.strip()
    df["cliente"] = df["cliente_raw"].str.strip()
    df["sku"] = df["sku_raw"].str.strip()

    df["qde_pedida"] = pd.to_numeric(df["qde_pedida_raw"].str.replace(",", "."), errors="coerce")

    df["dta_desejada_amer"] = pd.to_datetime(
        df["dta_desejada_raw"],
        format="%d/%m/%Y",
        errors="coerce"
    )

    return df


def preparar_faturamentos(df):
    df.columns = ["dta_efetiva_raw", "cliente_raw", "sku_raw", "qde_fatur_raw", "numero_ordem_raw"]

    df["numero_ordem"] = df["numero_ordem_raw"].str.strip()
    df["cliente_fatur"] = df["cliente_raw"].str.strip()
    df["sku"] = df["sku_raw"].str.strip()

    df["qde_fatur"] = pd.to_numeric(df["qde_fatur_raw"].str.replace(",", "."), errors="coerce")

    df["dta_efetiva_amer"] = pd.to_datetime(
        df["dta_efetiva_raw"],
        format="%d/%m/%Y",
        errors="coerce"
    )

    return df


# ---------- CRUZAMENTO ----------

def cruzar_pedidos_faturamentos(pedidos, fatur):
    ped_fatur = pedidos.merge(
        fatur,
        left_on=["ordem", "sku"],
        right_on=["numero_ordem", "sku"],
        how="left",
        suffixes=("", "_fat")
    )
    return ped_fatur


# ---------- CÁLCULO OTIF ----------

def calcular_otif(df):
    df["pontua_data"] = (
        df["dta_efetiva_amer"] <= df["dta_desejada_amer"]
    ).fillna(False).astype(int)

    df["pontua_qde"] = (
        df["qde_fatur"] >= df["qde_pedida"]
    ).fillna(False).astype(int)

    df["pontua_total"] = (
        (df["pontua_data"] + df["pontua_qde"]) == 2
    ).astype(int)

    return df


# ---------- CONSOLIDAÇÃO MENSAL ----------

def consolidar_mensal(df):
    df["ano"] = df["dta_desejada_amer"].dt.year.astype(int)
    df["mes"] = df["dta_desejada_amer"].dt.month.astype(int)

    consol = df.groupby(["ano", "mes"]).agg(
        total_linhas=("sku", "count"),
        linhas_atendidas=("pontua_total", "sum")
    ).reset_index()

    consol["nivel_servico"] = (
        consol["linhas_atendidas"] / consol["total_linhas"] * 100
    )

    return consol


# ---------- FUNÇÃO PRINCIPAL ----------

def processar_otif(pedidos_path, faturamentos_path):
    pedidos_raw = carregar_csv_duckdb(pedidos_path)
    fatur_raw = carregar_csv_duckdb(faturamentos_path)

    pedidos = preparar_pedidos(pedidos_raw)
    fatur = preparar_faturamentos(fatur_raw)

    ped_fatur = cruzar_pedidos_faturamentos(pedidos, fatur)
    ped_fatur = calcular_otif(ped_fatur)

    consol = consolidar_mensal(ped_fatur)

    # Gera o arquivo Excel
    arquivo_xlsx = "resultado_otif.xlsx"
    with pd.ExcelWriter(arquivo_xlsx) as writer:
        consol.to_excel(writer, sheet_name="Consolidado", index=False)
        ped_fatur.to_excel(writer, sheet_name="Detalhes", index=False)

    # Retorna apenas o caminho do arquivo (string)
    return arquivo_xlsx


# ---------- ENVIO DE E-MAIL ----------

def enviar_email_otif(destinatario, arquivo_xlsx):
    resend.api_key = os.getenv("RESEND_API_KEY")

    texto = "Prezado cliente,\n\n"
    texto += "Segue o resultado do processamento OTIF.\n\n"
    texto += "O arquivo Excel com o gráfico e consolidação está anexado.\n"
    texto += "\nAtenciosamente,\nMUPE Consultoria"

    with open(arquivo_xlsx, "rb") as f:
        conteudo_xlsx = f.read()

    resend.Emails.send({
        "from": "MUPE Consultoria <noreply@mupe.com.br>",
        "to": destinatario,
        "subject": "Resultado OTIF - MUPE Consultoria",
        "text": texto,
        "attachments": [
            {
                "filename": os.path.basename(arquivo_xlsx),
                "content": conteudo_xlsx,
                "type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
        ]
    })

    return True
