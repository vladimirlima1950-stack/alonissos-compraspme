import base64
import os
from datetime import datetime

import duckdb
import pandas as pd
import requests

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

app = FastAPI()

# ============================================================
# Configurações gerais e Diretórios
# ============================================================

OUTPUT_DIR = os.path.join("uploads", "output_relatorios")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def log(msg):
    log_line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(log_line)
    log_path = os.path.join("uploads", "log.txt")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except Exception as e:
        print(f"Falha ao escrever log: {e}")


# ============================================================
# Validações dos CSVs
# ============================================================


def validar_csv_pedidos(caminho_pedidos: str):
    if not os.path.exists(caminho_pedidos):
        return False, "Arquivo de pedidos não encontrado."
    try:
        # Removido sep="\t" para permitir que o DuckDB auto-detecte (vírgula, ponto e vírgula ou TAB)
        df = duckdb.read_csv(
            caminho_pedidos, 
            header=True, 
            auto_detect=True, 
            all_varchar=True
        ).df()
        
        if df.empty:
            return False, "Arquivo de pedidos está vazio."
            
        if df.shape[1] != 6:
            return (
                False,
                f"Arquivo de pedidos precisa ter 6 colunas (recebido: {df.shape[1]}). Verifique se o separador é vírgula, ponto e vírgula ou TAB.",
            )
    except Exception as e:
        return False, f"Erro ao ler pedidos: {e}"
    return True, "Arquivo de pedidos validado com sucesso."


def validar_csv_entregas(caminho_entregas: str):
    if not os.path.exists(caminho_entregas):
        return False, "Arquivo de entregas não encontrado."
    try:
        df = duckdb.read_csv(
            caminho_entregas, 
            header=True, 
            auto_detect=True, 
            all_varchar=True
        ).df()
        
        if df.empty:
            return False, "Arquivo de entregas está vazio."
            
        if df.shape[1] < 5:
            return (
                False,
                f"Arquivo de entregas precisa ter 5 colunas (recebido: {df.shape[1]}).",
            )
    except Exception as e:
        return False, f"Erro ao ler entregas: {e}"
    return True, "Arquivo de entregas validado com sucesso."


def validar_csv_leadtime(caminho_leadtime: str):
    if not os.path.exists(caminho_leadtime):
        return False, "Arquivo de leadtime não encontrado."
    try:
        df = duckdb.read_csv(
            caminho_leadtime, 
            header=True, 
            auto_detect=True, 
            all_varchar=True
        ).df()
        
        if df.empty:
            return False, "Arquivo de leadtime está vazio."
            
        if df.shape[1] < 3:
            return (
                False,
                f"Arquivo de leadtime precisa ter 3 colunas (recebido: {df.shape[1]}).",
            )
    except Exception as e:
        return False, f"Erro ao ler leadtime: {e}"
    return True, "Arquivo de leadtime validado com sucesso."

# ============================================================
# Endpoints HTTP (FastAPI)
# ============================================================

pedidos_path = None
entregas_path = None
leadtime_path = None

@app.post("/upload_pedidos")
async def upload_pedidos(file: UploadFile = File(...)):
    global pedidos_path
    pedidos_path = f"uploads/{file.filename}"
    with open(pedidos_path, "wb") as f:
        f.write(await file.read())

    ok, msg = validar_csv_pedidos(pedidos_path)
    if not ok:
        return JSONResponse(status_code=400, content={"status": "erro", "mensagem": msg})

    return {"status": "ok", "mensagem": "Pedidos recebidos e validados."}


@app.post("/upload_entregas")
async def upload_entregas(file: UploadFile = File(...)):
    global entregas_path
    entregas_path = f"uploads/{file.filename}"
    with open(entregas_path, "wb") as f:
        f.write(await file.read())

    ok, msg = validar_csv_entregas(entregas_path)
    if not ok:
        return JSONResponse(status_code=400, content={"status": "erro", "mensagem": msg})

    return {"status": "ok", "mensagem": "Entregas recebidas e validadas."}


@app.post("/upload_leadtime")
async def upload_leadtime(file: UploadFile = File(...)):
    global leadtime_path
    leadtime_path = f"uploads/{file.filename}"
    with open(leadtime_path, "wb") as f:
        f.write(await file.read())

    ok, msg = validar_csv_leadtime(leadtime_path)
    if not ok:
        return JSONResponse(status_code=400, content={"status": "erro", "mensagem": msg})

    return {"status": "ok", "mensagem": "Leadtime recebido e validado."}


# ============================================================
# Etapas do Pipeline SQL / DuckDB
# ============================================================

def sp0_criar_tabelas(con):
    con.execute("""
        DROP TABLE IF EXISTS tb_pedidos_orig;
        DROP TABLE IF EXISTS tb_entregas_orig;
        DROP TABLE IF EXISTS tb_leadtime_orig;

        CREATE TABLE tb_pedidos_orig (
            codigo_pedido VARCHAR,
            dta_pedido DATE,
            codigo_produto VARCHAR,
            codigo_fornecedor VARCHAR,
            dta_desejada DATE,
            qde_desejada DECIMAL(10,2)
        );

        CREATE TABLE tb_entregas_orig (
            codigo_pedido VARCHAR,
            codigo_produto VARCHAR,
            codigo_fornecedor VARCHAR,
            qde_entregue DECIMAL(10,2),
            dta_nota_fiscal DATE
        );

        CREATE TABLE tb_leadtime_orig (
            codigo_fornecedor VARCHAR,
            codigo_produto VARCHAR,
            leadtime_dias DECIMAL(10,2)
        );
    """)

def sp1_importar_e_limpar(con, arq_pedidos, arq_entregas, arq_leadtime):
    # Pedidos
    df_ped = pd.read_csv(arq_pedidos, sep=";", dtype=str)
    df_ped.columns = [
        "codigo_pedido",
        "dta_pedido",
        "codigo_produto",
        "codigo_fornecedor",
        "dta_desejada",
        "qde_desejada",
    ]

    df_ped["qde_desejada"] = (
        df_ped["qde_desejada"]
        .str.replace(",", ".", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0)
    )

    df_ped["dta_pedido"] = pd.to_datetime(df_ped["dta_pedido"], errors="coerce", dayfirst=True)
    df_ped["dta_desejada"] = pd.to_datetime(df_ped["dta_desejada"], errors="coerce", dayfirst=True)

    con.execute("DELETE FROM tb_pedidos_orig")
    con.register("df_pedidos_tmp", df_ped)
    con.execute("""
        INSERT INTO tb_pedidos_orig
        SELECT codigo_pedido,
               dta_pedido,
               codigo_produto,
               codigo_fornecedor,
               dta_desejada,
               qde_desejada
        FROM df_pedidos_tmp;
    """)

    # Entregas
    df_ent = pd.read_csv(arq_entregas, sep=";", dtype=str)
    df_ent.columns = [
        "codigo_pedido",
        "codigo_produto",
        "codigo_fornecedor",
        "qde_entregue",
        "dta_nota_fiscal",
    ]

    df_ent["qde_entregue"] = (
        df_ent["qde_entregue"]
        .str.replace(",", ".", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0)
    )

    df_ent["dta_nota_fiscal"] = pd.to_datetime(df_ent["dta_nota_fiscal"], errors="coerce", dayfirst=True)

    con.execute("DELETE FROM tb_entregas_orig")
    con.register("df_entregas_tmp", df_ent)
    con.execute("""
        INSERT INTO tb_entregas_orig
        SELECT codigo_pedido,
               codigo_produto,
               codigo_fornecedor,
               qde_entregue,
               dta_nota_fiscal
        FROM df_entregas_tmp;
    """)

    # Leadtime
    df_lead = pd.read_csv(arq_leadtime, sep=";", dtype=str)
    df_lead.columns = [
        "codigo_fornecedor",
        "codigo_produto",
        "leadtime_dias",
    ]

    df_lead["leadtime_dias"] = (
        df_lead["leadtime_dias"]
        .str.replace(",", ".", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0)
    )

    con.execute("DELETE FROM tb_leadtime_orig")
    con.register("df_leadtime_tmp", df_lead)
    con.execute("""
        INSERT INTO tb_leadtime_orig
        SELECT codigo_fornecedor,
               codigo_produto,
               leadtime_dias
        FROM df_leadtime_tmp;
    """)

def sp2_classificacao(con):
    con.execute("""
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

        ALTER TABLE tb_pedidos_entregas ADD COLUMN tipo_pedido VARCHAR;
        ALTER TABLE tb_pedidos_entregas ADD COLUMN lead_time INTEGER;

        UPDATE tb_pedidos_entregas
        SET lead_time = CAST(l.leadtime_dias AS INTEGER)
        FROM tb_leadtime_orig l
        WHERE tb_pedidos_entregas.codigo_fornecedor = l.codigo_fornecedor
          AND tb_pedidos_entregas.codigo_produto = l.codigo_produto;

        UPDATE tb_pedidos_entregas
        SET tipo_pedido = CASE
            WHEN datediff('day', dta_pedido, dta_desejada) >= lead_time THEN 'FLT'
            WHEN datediff('day', dta_pedido, dta_desejada) < lead_time THEN 'SLT'
            WHEN lead_time IS NULL THEN 'INDEF'
        END;
    """)

def sp3_pontuacoes(con):
    con.execute("""
        ALTER TABLE tb_pedidos_entregas ADD COLUMN dta_pontua DECIMAL(5,2);
        ALTER TABLE tb_pedidos_entregas ADD COLUMN qde_pontua DECIMAL(5,2);

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
            sum(COALESCE(qde_entregue, 0)) AS qde_entregue,
            max(dta_nota_fiscal) AS dta_nota_fiscal,
            max(dta_pontua) AS dta_pontua,
            sum(COALESCE(qde_pontua, 0)) AS qde_pontua
        FROM tb_pedidos_entregas
        GROUP BY codigo_pedido, codigo_produto, codigo_fornecedor;

        UPDATE tb_pedidos_entregas_resumo_fase2
        SET dta_pontua = CASE
            WHEN dta_nota_fiscal <= dta_desejada THEN 1 ELSE 0 END;

        UPDATE tb_pedidos_entregas_resumo_fase2
        SET qde_pontua = CASE
            WHEN qde_entregue >= qde_desejada THEN 1 ELSE 0 END;

        ALTER TABLE tb_pedidos_entregas_resumo_fase2 ADD COLUMN ano_mes VARCHAR;

        UPDATE tb_pedidos_entregas_resumo_fase2
        SET ano_mes = strftime(dta_desejada, '%Y-%m');

        ALTER TABLE tb_pedidos_entregas_resumo_fase2 ADD COLUMN dta_qde_pontua DECIMAL(5,2);

        UPDATE tb_pedidos_entregas_resumo_fase2
        SET dta_qde_pontua = 1
        WHERE tipo_pedido = 'FLT'
          AND dta_pontua = 1
          AND qde_pontua = 1;
    """)

def sp4_relatorios(con):
    con.execute("""
        DROP TABLE IF EXISTS tb_desempenho_global_fornecedor;

        CREATE TABLE tb_desempenho_global_fornecedor AS
        SELECT
            codigo_fornecedor,
            count(tipo_pedido) AS qtde_linhas_pedidas,
            sum(COALESCE(dta_qde_pontua, 0)) AS qtde_linhas_atendidas,
            (sum(COALESCE(dta_qde_pontua, 0)) * 100.0
             / NULLIF(count(tipo_pedido), 0)) AS desempenho_fornecedor
        FROM tb_pedidos_entregas_resumo_fase2
        WHERE lower(tipo_pedido) = 'flt'
        GROUP BY codigo_fornecedor
        ORDER BY codigo_fornecedor;

        DROP TABLE IF EXISTS tb_desempenho_mes_a_mes_fornecedor;

        CREATE TABLE tb_desempenho_mes_a_mes_fornecedor AS
        SELECT
            codigo_fornecedor,
            ano_mes,
            count(tipo_pedido) AS qtde_linhas_pedidas,
            sum(COALESCE(dta_qde_pontua, 0)) AS qtde_linhas_atendidas,
            (sum(COALESCE(dta_qde_pontua, 0)) * 100.0
             / NULLIF(count(tipo_pedido), 0)) AS desempenho_fornecedor
        FROM tb_pedidos_entregas_resumo_fase2
        WHERE lower(tipo_pedido) = 'flt'
        GROUP BY codigo_fornecedor, ano_mes
        ORDER BY codigo_fornecedor, ano_mes;

        DROP TABLE IF EXISTS tb_desempenho_mes_a_mes_planejamento;

        CREATE TABLE tb_desempenho_mes_a_mes_planejamento AS
        SELECT
            codigo_pedido,
            codigo_fornecedor,
            tipo_pedido,
            CASE WHEN tipo_pedido = 'FLT' THEN 1 ELSE 0 END AS pedido_FLT,
            CASE WHEN tipo_pedido = 'SLT' THEN 1 ELSE 0 END AS pedido_SLT,
            ano_mes
        FROM tb_pedidos_entregas_resumo_fase2;

        DROP TABLE IF EXISTS tb_desempenho_mes_a_mes_planejamento_resumo;

        CREATE TABLE tb_desempenho_mes_a_mes_planejamento_resumo AS
        SELECT
            codigo_fornecedor,
            sum(pedido_FLT) AS pedido_FLT,
            sum(pedido_SLT) AS pedido_SLT,
            ano_mes,
            (sum(pedido_FLT) + sum(pedido_SLT)) AS pedidos_colocados_total,
            (sum(pedido_FLT) * 100.0
             / NULLIF(sum(pedido_FLT) + sum(pedido_SLT), 0)) AS efetividade_planejamento
        FROM tb_desempenho_mes_a_mes_planejamento
        GROUP BY codigo_fornecedor, ano_mes
        ORDER BY codigo_fornecedor, ano_mes;

        DROP TABLE IF EXISTS tb_desempenho_global_planejamento_resumo;

        CREATE TABLE tb_desempenho_global_planejamento_resumo AS
        SELECT
            codigo_fornecedor,
            sum(pedido_FLT) AS pedido_FLT,
            sum(pedido_SLT) AS pedido_SLT,
            (sum(pedido_FLT) + sum(pedido_SLT)) AS pedidos_colocados_total,
            (sum(pedido_FLT) * 100.0
             / NULLIF(sum(pedido_FLT) + sum(pedido_SLT), 0)) AS efetividade_planejamento
        FROM tb_desempenho_mes_a_mes_planejamento
        GROUP BY codigo_fornecedor
        ORDER BY codigo_fornecedor;

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
# Exportação Excel (.xlsx)
# ============================================================

def exportar_relatorios(con):
    # Caminho do arquivo final
    arquivo_xlsx = os.path.join(
        OUTPUT_DIR,
        f"COMPRAS_PME_AVAL_FORNEC_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )

    # Mapeamento das abas → tabelas SQL
    tabelas = {
        "Desempenho_Global_Forn": "tb_desempenho_global_fornecedor",
        "Desempenho_Mes_Forn": "tb_desempenho_mes_a_mes_fornecedor",
        "Planejamento_Mes": "tb_desempenho_mes_a_mes_planejamento_resumo",
        "Planejamento_Global": "tb_desempenho_global_planejamento_resumo",
        "Leadtime_Faltante": "tb_leadtime_faltante",
    }

    # criar Excel com engine mais estável
    with pd.ExcelWriter(arquivo_xlsx, engine="xlsxwriter") as writer:
        workbook = writer.book
        percent_fmt = workbook.add_format({'num_format': '0.00%'})

        for aba, tabela in tabelas.items():
            try:
                existe = con.execute(
                    f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{tabela}'"
                ).fetchone()[0]

                if existe == 0:
                    df_vazio = pd.DataFrame({"Aviso": [f"Tabela {tabela} não existe."]})
                    df_vazio.to_excel(writer, sheet_name=aba, index=False)
                    continue

                df = con.execute(f"SELECT * FROM {tabela}").df()

                if df.empty:
                    df_vazio = pd.DataFrame({"Aviso": [f"Tabela {tabela} está vazia."]})
                    df_vazio.to_excel(writer, sheet_name=aba, index=False)
                    continue

                df.to_excel(writer, sheet_name=aba, index=False)

                # === APLICA FORMATAÇÃO DE PERCENTUAL ===
                worksheet = writer.sheets[aba]

                # Colunas que devem ser formatadas como percentual
                colunas_percentuais = [
                    "desempenho_fornecedor",
                    "efetividade_planejamento"
            ]

                for col_idx, col_name in enumerate(df.columns):
                    if col_name.lower() in colunas_percentuais:
                        worksheet.set_column(col_idx, col_idx, 12, percent_fmt)

            except Exception as e:
                df_erro = pd.DataFrame({"Erro": [f"Falha ao exportar {tabela}: {e}"]})
                df_erro.to_excel(writer, sheet_name=f"{aba}_ERRO", index=False)


    log(f"Arquivo Excel unificado gerado: {arquivo_xlsx}")
    return arquivo_xlsx


# ============================================================
# Função principal do pipeline
# ============================================================


def processar_compraspme(pedidos: str, entregas: str, leadtime: str):
    try:
        log("############################################################")
        log(
            f"# COMPRAS PME EXECUTADO EM {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        log("############################################################")

        con = duckdb.connect(":memory:")
        log("Conexão DuckDB em memória estabelecida.")

        log("Criando tabelas iniciais...")
        sp0_criar_tabelas(con)

        log("Importando e tratando arquivos CSV...")
        sp1_importar_e_limpar(con, pedidos, entregas, leadtime)

        log("Executando classificação FLT/SLT...")
        sp2_classificacao(con)

        log("Calculando pontuações...")
        sp3_pontuacoes(con)

        log("Gerando relatórios...")
        sp4_relatorios(con)

        log("Exportando Excel...")
        arquivo_xlsx = exportar_relatorios(con)

        con.close()
        log("Processamento concluído com sucesso.")

        return arquivo_xlsx

    except Exception as e:
        log(f"Erro interno no processamento: {e}")
        raise Exception(f"Falha ao processar ComprasPME: {e}")


# ============================================================
# Envio de e-mail via Resend API
# ============================================================


def enviar_email_relatorio(arquivo_xlsx: str, email_destino: str, nome_cliente: str):
    log(f"Enviando relatório PME para {email_destino} via Resend...")

    RESEND_API_KEY = os.getenv("RESEND_API_KEY")
    print("RESEND_API_KEY no módulo:", RESEND_API_KEY)
    

    if not RESEND_API_KEY:
        log("ERRO: RESEND_API_KEY não configurada.")
        return False

    # CORRIGIDO: bloco try/except recuado para dentro da função
    try:
        with open(arquivo_xlsx, "rb") as f:
            arquivo_bytes = f.read()
            arquivo_base64 = base64.b64encode(arquivo_bytes).decode("utf-8")

        payload = {
            "from": "MUPE Consultoria <noreply@mupeconsult.com>",
             "to": email_destino,
            "subject": "Relatório Avaliação de Fornecedores - ComprasPME",
            "html": (
    f"<p>Olá, {nome_cliente}.</p>"
    "<p>Os seus arquivos foram processados com sucesso e estamos anexando nesta mensagem a planilha resultante.</p>"
    "<p>Caso haja qualquer dúvida, sugestão ou dificuldade, por favor entre em contato conosco.</p>"
    "</p>Será um prazer ajudar.</p>"
    "<p>Atenciosamente,<br>"
    "<strong>MUPE Consultoria</strong><br>"
    "</p>"
),
            "attachments": [
                {
                    "filename": os.path.basename(arquivo_xlsx),
                    "content": arquivo_base64,
                    "type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                }
            ],
        }

        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )

        if 200 <= response.status_code < 300:
            log("E-mail enviado com sucesso.")
            return True
        else:
            log(
                f"Erro ao enviar e-mail via Resend API: {response.status_code} - {response.text}"
            )
            return False

    except Exception as e:
        log(f"Erro ao enviar e-mail via Resend API: {e}")
        return False
    
   