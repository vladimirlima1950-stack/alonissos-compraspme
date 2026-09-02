import pandas as pd
import duckdb


def carregar_csv_duckdb(path):
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_csv_auto('{path}')").df()
    con.close()
    return df


def preparar_pedidos(df):
    df["qde_pedida"] = df["qde_pedida"].astype(float)
    df["dta_desejada_amer"] = pd.to_datetime(df["dta_desejada"], dayfirst=True)
    return df


def preparar_faturamentos(df):
    df["qde_fatur"] = df["qde_fatur"].astype(float)
    df["dta_efetiva_amer"] = pd.to_datetime(df["dta_efetiva"], dayfirst=True)
    return df


def cruzar_pedidos_faturamentos(pedidos, fatur):
    ped_fatur = pedidos.merge(
        fatur,
        left_on=["ordem", "sku"],
        right_on=["numero_ordem", "sku"],
        how="left"
    )
    return ped_fatur


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


def consolidar_mensal(df):
    df["ano"] = df["dta_desejada_amer"].dt.year
    df["mes"] = df["dta_desejada_amer"].dt.month

    consol = df.groupby(["ano", "mes"]).agg(
        total_linhas=("sku", "count"),
        linhas_atendidas=("pontua_total", "sum")
    ).reset_index()

    consol["nivel_servico"] = (
        consol["linhas_atendidas"] / consol["total_linhas"] * 100
    )

    return consol


def processar_otif(pedidos_path, faturamentos_path):
    # Carregar arquivos
    pedidos = carregar_csv_duckdb(pedidos_path)
    fatur = carregar_csv_duckdb(faturamentos_path)

    # Preparar dados
    pedidos = preparar_pedidos(pedidos)
    fatur = preparar_faturamentos(fatur)

    # Cruzar
    ped_fatur = cruzar_pedidos_faturamentos(pedidos, fatur)

    # Calcular OTIF
    ped_fatur = calcular_otif(ped_fatur)

    # Consolidação mensal
    consol = consolidar_mensal(ped_fatur)

    return consol
