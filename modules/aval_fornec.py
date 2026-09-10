import duckdb
import os

# ============================================================
# Configurações gerais
# ============================================================

ARQ_PEDIDOS = "compras_pedidos.csv"
ARQ_ENTREGAS = "compras_entregas.csv"
ARQ_LEADTIME = "compras_leadtime.csv"

OUTPUT_DIR = "output_relatorios"
os.makedirs(OUTPUT_DIR, exist_ok=True)

con = duckdb.connect("compras_pme.duckdb")

# ============================================================
# Função utilitária para executar SQL com log
# ============================================================

def run(sql):
    print("\nExecutando bloco SQL...")
    con.execute(sql)

# ============================================================
# SP0 – Criação das tabelas originais
# ============================================================

def sp0_criar_tabelas():
    run("""
    DROP TABLE IF EXISTS tb_pedidos_orig;
    DROP TABLE IF EXISTS tb_entregas_orig;
    DROP TABLE IF EXISTS tb_leadtime_orig;
    DROP TABLE IF EXISTS tb_tempo_procedure;
    """)

    run("""
    CREATE TABLE tb_pedidos_orig (
        codigo_pedido VARCHAR,
        dta_pedido VARCHAR,
        codigo_produto VARCHAR,
        codigo_fornecedor VARCHAR,
        dta_desejada VARCHAR,
        qde_desejada VARCHAR
    );
    """)

    run("""
    CREATE TABLE tb_entregas_orig (
        codigo_pedido VARCHAR,
        codigo_produto VARCHAR,
        codigo_fornecedor VARCHAR,
        qde_entregue VARCHAR,
        dta_nota_fiscal VARCHAR
    );
    """)

    run("""
    CREATE TABLE tb_leadtime_orig (
        codigo_fornecedor VARCHAR,
        codigo_produto VARCHAR,
        leadtime_dias VARCHAR
    );
    """)

    run("""
    CREATE TABLE tb_tempo_procedure (
        nome_procedure VARCHAR,
        inicio TIMESTAMP,
        final TIMESTAMP,
        tempo_minutos DECIMAL(5,2)
    );
    """)

# ============================================================
# SP1 – Importação e limpeza de dados
# ============================================================

def sp1_importar_e_limpar():
    run(f"""
    INSERT INTO tb_pedidos_orig
    SELECT * FROM read_csv_auto('{ARQ_PEDIDOS}', header=True);
    """)

    run(f"""
    INSERT INTO tb_entregas_orig
    SELECT * FROM read_csv_auto('{ARQ_ENTREGAS}', header=True);
    """)

    run(f"""
    INSERT INTO tb_leadtime_orig
    SELECT * FROM read_csv_auto('{ARQ_LEADTIME}', header=True);
    """)

    # Limpeza e conversões
    run("""
    UPDATE tb_pedidos_orig
    SET qde_desejada = replace(qde_desejada, ',', '.');
    """)

    run("""
    ALTER TABLE tb_pedidos_orig
    ALTER COLUMN qde_desejada TYPE DECIMAL(10,2)
    USING CAST(qde_desejada AS DECIMAL(10,2));
    """)

    run("""
    UPDATE tb_pedidos_orig
    SET dta_pedido = strptime(dta_pedido, '%d/%m/%Y'),
        dta_desejada = strptime(dta_desejada, '%d/%m/%Y');
    """)

    run("""
    UPDATE tb_entregas_orig
    SET qde_entregue = replace(qde_entregue, ',', '.');
    """)

    run("""
    ALTER TABLE tb_entregas_orig
    ALTER COLUMN qde_entregue TYPE DECIMAL(10,2)
    USING CAST(qde_entregue AS DECIMAL(10,2));
    """)

    run("""
    UPDATE tb_entregas_orig
    SET dta_nota_fiscal = strptime(dta_nota_fiscal, '%d/%m/%Y');
    """)

    run("""
    UPDATE tb_leadtime_orig
    SET leadtime_dias = replace(leadtime_dias, ',', '.');
    """)

    run("""
    ALTER TABLE tb_leadtime_orig
    ALTER COLUMN leadtime_dias TYPE DECIMAL(10,2)
    USING CAST(leadtime_dias AS DECIMAL(10,2));
    """)

    # Tabelas resumo
    run("""
    DROP TABLE IF EXISTS tb_pedidos_resumo;
    CREATE TABLE tb_pedidos_resumo AS
    SELECT
        codigo_pedido,
        codigo_produto,
        codigo_fornecedor,
        dta_pedido,
        max(dta_desejada) AS dta_desejada,
        sum(qde_desejada) AS qde_desejada
    FROM tb_pedidos_orig
    GROUP BY codigo_pedido, codigo_produto, codigo_fornecedor, dta_pedido;
    """)

    run("""
    DROP TABLE IF EXISTS tb_entregas_resumo;
    CREATE TABLE tb_entregas_resumo AS
    SELECT
        codigo_pedido,
        codigo_produto,
        codigo_fornecedor,
        sum(qde_entregue) AS qde_entregue,
        max(dta_nota_fiscal) AS dta_nota_fiscal
    FROM tb_entregas_orig
    GROUP BY codigo_pedido, codigo_produto, codigo_fornecedor;
    """)

    run("""
    DROP TABLE IF EXISTS tb_leadtime_resumo;
    CREATE TABLE tb_leadtime_resumo AS
    SELECT
        codigo_fornecedor,
        codigo_produto,
        max(leadtime_dias) AS leadtime_dias
    FROM tb_leadtime_orig
    GROUP BY codigo_fornecedor, codigo_produto;
    """)

# ============================================================
# SP2 – Classificação FLT/SLT
# ============================================================

def sp2_classificacao():
    run("""
    DROP TABLE IF EXISTS tb_pedidos_entregas;
    CREATE TABLE tb_pedidos_entregas AS
    SELECT
        p.codigo_pedido,
        p.dta_pedido,
        p.codigo_produto,
        p.codigo_fornecedor,
        p.dta_desejada,
        p.qde_desejada,
        e.qde_entregue,
        e.dta_nota_fiscal
    FROM tb_pedidos_orig p
    LEFT JOIN tb_entregas_orig e
    ON p.codigo_pedido = e.codigo_pedido
    AND p.codigo_fornecedor = e.codigo_fornecedor
    AND p.codigo_produto = e.codigo_produto;
    """)

    run("""
    ALTER TABLE tb_pedidos_entregas ADD COLUMN tipo_pedido VARCHAR;
    ALTER TABLE tb_pedidos_entregas ADD COLUMN lead_time INTEGER;
    """)

    run("""
    UPDATE tb_pedidos_entregas
    SET lead_time = CAST(l.leadtime_dias AS INTEGER)
    FROM tb_leadtime_resumo l
    WHERE tb_pedidos_entregas.codigo_fornecedor = l.codigo_fornecedor
    AND tb_pedidos_entregas.codigo_produto = l.codigo_produto;
    """)

    run("""
    UPDATE tb_pedidos_entregas
    SET tipo_pedido =
        CASE
            WHEN datediff('day', dta_pedido, dta_desejada) >= lead_time THEN 'FLT'
            WHEN datediff('day', dta_pedido, dta_desejada) < lead_time THEN 'SLT'
            WHEN lead_time IS NULL THEN 'INDEF'
        END;
    """)

# ============================================================
# SP3 – Pontuações
# ============================================================

def sp3_pontuacoes():
    run("""
    ALTER TABLE tb_pedidos_entregas ADD COLUMN dta_pontua DECIMAL(5,2);
    ALTER TABLE tb_pedidos_entregas ADD COLUMN qde_pontua DECIMAL(5,2);
    """)

    # Fase 1
    run("""
    DROP TABLE IF EXISTS tb_pedidos_entregas_resumo_fase1;
    CREATE TABLE tb_pedidos_entregas_resumo_fase1 AS
    SELECT
        codigo_pedido,
        codigo_produto,
        codigo_fornecedor,
        max(dta_desejada) AS dta_desejada,
        max(lead_time) AS lead_time,
        max(tipo_pedido) AS tipo_pedido,
        max(qde_desejada) AS qde_desejada,
        sum(qde_entregue) AS qde_entregue,
        dta_nota_fiscal,
        max(dta_pontua) AS dta_pontua,
        sum(qde_pontua) AS qde_pontua
    FROM tb_pedidos_entregas
    GROUP BY codigo_pedido, codigo_produto, codigo_fornecedor, dta_nota_fiscal;
    """)

    run("""
    ALTER TABLE tb_pedidos_entregas_resumo_fase1 ADD COLUMN inf_plan DECIMAL(5,2);
    ALTER TABLE tb_pedidos_entregas_resumo_fase1 DROP COLUMN dta_pedido;
    """)

    # Fase 2
    run("""
    DROP TABLE IF EXISTS tb_pedidos_entregas_resumo_fase2;
    CREATE TABLE tb_pedidos_entregas_resumo_fase2 AS
    SELECT
        codigo_pedido,
        codigo_produto,
        codigo_fornecedor,
        max(dta_desejada) AS dta_desejada,
        max(lead_time) AS lead_time,
        max(tipo_pedido) AS tipo_pedido,
        max(qde_desejada) AS qde_desejada,
        sum(qde_entregue) AS qde_entregue,
        max(dta_nota_fiscal) AS dta_nota_fiscal,
        max(dta_pontua) AS dta_pontua,
        sum(qde_pontua) AS qde_pontua
    FROM tb_pedidos_entregas
    GROUP BY codigo_pedido, codigo_produto, codigo_fornecedor;
    """)

    # Pontuações
    run("""
    UPDATE tb_pedidos_entregas_resumo_fase2
    SET dta_pontua =
        CASE
            WHEN dta_nota_fiscal <= dta_desejada THEN 1
            WHEN dta_nota_fiscal > dta_desejada THEN 0
            WHEN dta_nota_fiscal IS NULL THEN 0
        END;
    """)

    run("""
    UPDATE tb_pedidos_entregas_resumo_fase2
    SET qde_pontua =
        CASE
            WHEN qde_entregue >= qde_desejada THEN 1
            WHEN qde_entregue < qde_desejada THEN 0
            WHEN qde_entregue IS NULL THEN 0
        END;
    """)

    run("""
    UPDATE tb_pedidos_entregas_resumo_fase2
    SET inf_plan =
        CASE
            WHEN tipo_pedido = 'FLT' THEN 1
            WHEN tipo_pedido = 'SLT' THEN 0
        END;
    """)

    run("""
    ALTER TABLE tb_pedidos_entregas_resumo_fase2 ADD COLUMN ano_mes VARCHAR;
    """)

    run("""
    UPDATE tb_pedidos_entregas_resumo_fase2
    SET ano_mes =
        CASE
            WHEN EXTRACT(MONTH FROM dta_desejada) >= 10
            THEN concat(EXTRACT(YEAR FROM dta_desejada), '-', EXTRACT(MONTH FROM dta_desejada))
            ELSE concat(EXTRACT(YEAR FROM dta_desejada), '-0', EXTRACT(MONTH FROM dta_desejada))
        END;
    """)

    run("""
    ALTER TABLE tb_pedidos_entregas_resumo_fase2 ADD COLUMN dta_qde_pontua DECIMAL(5,2);
    """)

    run("""
    UPDATE tb_pedidos_entregas_resumo_fase2
    SET dta_qde_pontua = 1
    WHERE tipo_pedido = 'FLT' AND dta_pontua = 1 AND qde_pontua = 1;
    """)

# ============================================================
# SP4 – Relatórios
# ============================================================

def sp4_relatorios():
    run("""
    DROP TABLE IF EXISTS tb_desempenho_global_fornecedor;
    CREATE TABLE tb_desempenho_global_fornecedor AS
    SELECT
        codigo_fornecedor,
        count(tipo_pedido) AS qtde_linhas_pedidas,
        sum(dta_qde_pontua) AS qtde_linhas_atendidas,
        (sum(dta_qde_pontua) * 100.0 / NULLIF(count(tipo_pedido),0)) AS desempenho_fornecedor
    FROM tb_pedidos_entregas_resumo_fase2
    WHERE lower(tipo_pedido) = 'flt'
    GROUP BY codigo_fornecedor, ano_mes
    ORDER BY codigo_fornecedor, ano_mes;
    """)

    run("""
    DROP TABLE IF EXISTS tb_desempenho_mes_a_mes_fornecedor;
    CREATE TABLE tb_desempenho_mes_a_mes_fornecedor AS
    SELECT
        codigo_fornecedor,
        ano_mes,
        count(tipo_pedido) AS qtde_linhas_pedidas,
        sum(dta_qde_pontua) AS qtde_linhas_atendidas,
        (sum(dta_qde_pontua) * 100.0 / NULLIF(count(tipo_pedido),0)) AS desempenho_fornecedor
    FROM tb_pedidos_entregas_resumo_fase2
    WHERE lower(tipo_pedido) = 'flt'
    GROUP BY codigo_fornecedor, ano_mes
    ORDER BY codigo_fornecedor, ano_mes;
    """)

    run("""
    DROP TABLE IF EXISTS tb_desempenho_mes_a_mes_planejamento;
    CREATE TABLE tb_desempenho_mes_a_mes_planejamento AS
    SELECT
        codigo_pedido,
        codigo_fornecedor,
        tipo_pedido,
        0 AS pedido_FLT,
        0 AS pedido_SLT,
        ano_mes,
        CAST(NULL AS DECIMAL(5,2)) AS efetividade_planejamento
    FROM tb_pedidos_entregas_resumo_fase2;
    """)

    run("""
    UPDATE tb_desempenho_mes_a_mes_planejamento
    SET pedido_FLT = 1
    WHERE tipo_pedido = 'FLT';
    """)

    run("""
    UPDATE tb_desempenho_mes_a_mes_planejamento
    SET pedido_SLT = 1
    WHERE tipo_pedido = 'SLT';
    """)

    run("""
    UPDATE tb_desempenho_mes_a_mes_planejamento
    SET pedido_FLT = 0
    WHERE tipo_pedido <> 'FLT' OR tipo_pedido IS NULL;
    """)

    run("""
    UPDATE tb_desempenho_mes_a_mes_planejamento
    SET pedido_SLT = 0
    WHERE tipo_pedido <> 'SLT' OR tipo_pedido IS NULL;
    """)

    run("""
    DROP TABLE IF EXISTS tb_desempenho_mes_a_mes_planejamento_resumo;
    CREATE TABLE tb_desempenho_mes_a_mes_planejamento_resumo AS
    SELECT
        codigo_fornecedor,
        sum(pedido_FLT) AS pedido_FLT,
        sum(pedido_SLT) AS pedido_SLT,
        ano_mes,
        (sum(pedido_FLT) + sum(pedido_SLT)) AS pedidos_colocados_total,
        (sum(pedido_FLT) * 100.0 / NULLIF(sum(pedido_FLT) + sum(pedido_SLT),0)) AS efetividade_planejamento
    FROM tb_desempenho_mes_a_mes_planejamento
    GROUP BY codigo_fornecedor, ano_mes
    ORDER BY codigo_fornecedor, ano_mes;
    """)

    run("""
    DROP TABLE IF EXISTS tb_desempenho_global_planejamento_resumo;
    CREATE TABLE tb_desempenho_global_planejamento_resumo AS
    SELECT
        codigo_fornecedor,
        sum(pedido_FLT) AS pedido_FLT,
        sum(pedido_SLT) AS pedido_SLT,
        (sum(pedido_FLT) + sum(pedido_SLT)) AS pedidos_colocados_total,
        (sum(pedido_FLT) * 100.0 / NULLIF(sum(pedido_FLT) + sum(pedido_SLT),0)) AS efetividade_planejamento
    FROM tb_desempenho_mes_a_mes_planejamento
    GROUP BY codigo_fornecedor
    ORDER BY codigo_fornecedor;
    """)

    run("""
    DROP TABLE IF EXISTS tb_leadtime_faltante;
    CREATE TABLE tb_leadtime_faltante AS
    SELECT
        codigo_produto,
        codigo_fornecedor,
        lead_time
    FROM tb_pedidos_entregas_resumo_fase2
    WHERE lead_time IS NULL;
    """)

# ============================================================
# Exportação
# ============================================================

def exportar_relatorios():

    def export_table(table_name):
        out_path = os.path.join(OUTPUT_DIR, f"{table_name}.csv")
        con.execute(f"COPY {table_name} TO '{out_path}' (FORMAT CSV, HEADER TRUE);")
        print(f"Exportado: {out_path}")

    tabelas = [
        "tb_desempenho_global_fornecedor",
        "tb_desempenho_mes_a_mes_fornecedor",
        "tb_desempenho_mes_a_mes_planejamento_resumo",
        "tb_desempenho_global_planejamento_resumo",
        "tb_leadtime_faltante"
    ]

    for t in tabelas:
        export_table(t)

# ============================================================
# Execução principal
# ============================================================

def main():
    print("\nIniciando processamento...")
    sp0_criar_tabelas()
    sp1_importar_e_limpar()
    sp2_classificacao()
    sp3_pontuacoes()
    sp4_relatorios()
    exportar_relatorios()
    con.close()
    print("\nProcessamento concluído com sucesso!")

# ============================================================
# FUNÇÕES FALTANTES — adicionadas para compatibilidade com main.py
# ============================================================

def validar_csv_pedidos(caminho):
    import csv
    try:
        with open(caminho, encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None:
                return False, "Arquivo de pedidos vazio."
        return True, "OK"
    except Exception as e:
        return False, f"Erro ao validar pedidos: {str(e)}"


def validar_csv_entregas(caminho):
    import csv
    try:
        with open(caminho, encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None:
                return False, "Arquivo