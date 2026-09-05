<?php
session_start();

// --- Segurança básica de sessão ---
if (!isset($_SESSION['logado']) || $_SESSION['logado'] !== true) {
    header("Location: login.php");
    exit;
}

session_regenerate_id(true);

$cliente      = $_SESSION['usuario'] ?? 'Desconhecido';
$railway_base = "https://cozy-vision-production-6526.up.railway.app";

// --- Função para enviar arquivo ao Railway ---
function enviarArquivo(string $campo, string $endpoint, string $railway_base): array
{
    if (!isset($_FILES[$campo]) || $_FILES[$campo]['error'] !== UPLOAD_ERR_OK) {
        return [
            'status'  => 'erro',
            'mensagem'=> "Arquivo '$campo' não enviado ou erro no upload."
        ];
    }

    $arquivo = $_FILES[$campo];

    // Tamanho mínimo (evita arquivo vazio)
    if ($arquivo['size'] < 10) {
        return [
            'status'  => 'erro',
            'mensagem'=> "Erro: o arquivo '$campo' está vazio ou muito pequeno."
        ];
    }

    // Verifica extensão .csv
    $ext = strtolower(pathinfo($arquivo['name'], PATHINFO_EXTENSION));
    if ($ext !== "csv") {
        return [
            'status'  => 'erro',
            'mensagem'=> "Erro: o arquivo enviado em '$campo' deve ser .csv"
        ];
    }

    // Verifica MIME (melhor que confiar só em $arquivo['type'])
    $mime = mime_content_type($arquivo['tmp_name']);
    if ($mime !== "text/plain" && $mime !== "text/csv" && $mime !== "application/vnd.ms-excel") {
        return [
            'status'  => 'erro',
            'mensagem'=> "Erro: o arquivo '$campo' não parece ser um CSV válido (MIME: $mime)."
        ];
    }

    // Sanitiza nome do arquivo
    $nomeSeguro = basename($arquivo['name']);

    // Envio via cURL
    $curl = curl_init();
    curl_setopt_array($curl, [
        CURLOPT_URL            => "$railway_base/$endpoint",
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => [
            "file" => curl_file_create(
                $arquivo['tmp_name'],
                $mime,
                $nomeSeguro
            )
        ],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 60
    ]);

    $resposta = curl_exec($curl);
    $erroCurl = curl_error($curl);
    curl_close($curl);

    if ($erroCurl) {
        return [
            'status'  => 'erro',
            'mensagem'=> "Erro ao enviar '$campo' para o servidor: $erroCurl"
        ];
    }

    // Espera que o backend Railway retorne JSON, ex:
    // { "status": "ok", "arquivo": "pedidos.csv", "mensagem": "Upload concluído" }
    $json = json_decode($resposta, true);

    if (!$json || !isset($json['status'])) {
        return [
            'status'  => 'erro',
            'mensagem'=> "Resposta inválida do servidor para '$campo': " . htmlspecialchars($resposta)
        ];
    }

    return $json;
}

$mensagens  = [];
$processado = false;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {

    // Envio dos arquivos
    $respPedidos      = enviarArquivo("pedidos", "upload_pedidos", $railway_base);
    $respFaturamentos = enviarArquivo("faturamentos", "upload_faturamentos", $railway_base);

    $mensagens[] = "Pedidos: "      . ($respPedidos['mensagem']      ?? '');
    $mensagens[] = "Faturamentos: " . ($respFaturamentos['mensagem'] ?? '');

    $pedidosOK      = isset($respPedidos['status'])      && $respPedidos['status']      === 'ok';
    $faturamentosOK = isset($respFaturamentos['status']) && $respFaturamentos['status'] === 'ok';

    if ($pedidosOK && $faturamentosOK) {
        // Chama o processamento OTIF
        $curl = curl_init();
        curl_setopt_array($curl, [
            CURLOPT_URL            => "$railway_base/processar_otif",
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 120
        ]);

        $respostaProcessamento = curl_exec($curl);
        $erroCurlProc          = curl_error($curl);
        curl_close($curl);

        if ($erroCurlProc) {
            $mensagens[] = "Erro ao processar OTIF: $erroCurlProc";
        } else {
            // Espera JSON também, ex:
            // { "status": "ok", "mensagem": "Processamento concluído" }
            $jsonProc = json_decode($respostaProcessamento, true);
            if ($jsonProc && isset($jsonProc['status']) && $jsonProc['status'] === 'ok') {
                $mensagens[] = "Processamento: " . ($jsonProc['mensagem'] ?? 'Concluído.');
                $processado  = true;
            } else {
                $mensagens[] = "Resposta inválida do processamento OTIF: " . htmlspecialchars($respostaProcessamento);
            }
        }
    } else {
        $mensagens[] = "Processamento OTIF não foi iniciado porque um ou ambos os arquivos apresentaram erro.";
    }
}
?>
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Envio de Arquivos OTIF - MUPE Consultoria</title>

<style>
body {
    font-family: Arial, sans-serif;
    background: #f3f4f6;
    margin: 0;
    padding: 0;
}

.container {
    max-width: 700px;
    margin: 40px auto;
    background: #ffffff;
    padding: 30px;
    border-radius: 10px;
    box-shadow: 0 8px 20px rgba(0,0,0,0.08);
}

h2 {
    margin-top: 0;
    font-size: 24px;
    color: #1f2933;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 8px;
}

h3 {
    margin-top: 25px;
    color: #374151;
}

.instrucoes {
    background:#eef6ff;
    padding:20px;
    border-radius:8px;
    border-left:5px solid #3b82f6;
    margin-bottom:25px;
}

.instrucoes h3 {
    margin-top:0;
    color:#1e3a8a;
}

input[type="file"] {
    margin-top: 5px;
}

button {
    width: 100%;
    padding: 12px;
    background: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    font-size: 15px;
    cursor: pointer;
    margin-top: 20px;
}

button:hover {
    background: #1d4ed8;
}

button:disabled {
    background: #9ca3af;
    cursor: not-allowed;
}

.msg {
    background: #e0f2fe;
    padding: 10px;
    border-radius: 6px;
    margin-top: 15px;
    color: #0369a1;
    font-size: 14px;
}

.sucesso {
    background: #dcfce7;
    padding: 15px;
    border-radius: 6px;
    margin-top: 20px;
    color: #166534;
    font-size: 15px;
    border-left: 5px solid #16a34a;
}

#loader {
    display: none;
    text-align: center;
    margin-top: 25px;
}

.spinner {
    width: 50px;
    height: 50px;
    border: 6px solid #e5e7eb;
    border-top-color: #2563eb;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: auto;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

#loader p {
    margin-top: 12px;
    font-size: 15px;
    color: #374151;
}
</style>

</head>

<body>

<div class="container">

<h2>Envio de Arquivos OTIF</h2>

<p>Cliente identificado: <strong><?= htmlspecialchars($cliente) ?></strong></p>

<div class="instrucoes">
    <h3>Instruções para o envio dos arquivos OTIF</h3>

    <p><strong>Antes de enviar os arquivos, verifique atentamente:</strong></p>

    <h4>Arquivo de Pedidos (CSV)</h4>
    <ul>
        <li>O arquivo deve conter <strong>5 colunas</strong> na seguinte ordem:</li>
        <li>1) Número da ordem</li>
        <li>2) Identificação do cliente</li>
        <li>3) Data desejada (formato <strong>DD/MM/AAAA</strong>)</li>
        <li>4) Número do item / peça / artigo / SKU</li>
        <li>5) Quantidade desejada</li>
        <li>Apenas a <strong>3ª coluna</strong> deve estar em formato de data.</li>
        <li>Todas as demais colunas devem ser formatadas como <strong>texto</strong>.</li>
        <li>O arquivo deve ser salvo com extensão <strong>.csv</strong>.</li>
    </ul>

    <h4>Arquivo de Faturamentos (CSV)</h4>
    <ul>
        <li>O arquivo deve conter <strong>5 colunas</strong> na seguinte ordem:</li>
        <li>1) Data do faturamento (formato <strong>DD/MM/AAAA</strong>)</li>
        <li>2) Identificação do cliente</li>
        <li>3) Número do item / peça / artigo / SKU</li>
        <li>4) Quantidade faturada</li>
        <li>5) Ordem de venda</li>
        <li>Apenas a <strong>1ª coluna</strong> deve estar em formato de data.</li>
        <li>Todas as demais colunas devem ser formatadas como <strong>texto</strong>.</li>
        <li>O arquivo deve ser salvo com extensão <strong>.csv</strong>.</li>
    </ul>
</div>

<div id="loader">
    <div class="spinner"></div>
    <p>Enviando arquivos... Aguarde.</p>
</div>

<form method="POST" enctype="multipart/form-data">

<h3>Arquivo de Pedidos (.csv)</h3>
<input type="file" name="pedidos" required>

<h3>Arquivo de Faturamentos (.csv)</h3>
<input type="file" name="faturamentos" required>

<button type="submit">Enviar arquivos e processar OTIF</button>

</form>

<?php if (!empty($mensagens)): ?>
<div class="msg">
    <?php foreach ($mensagens as $m): ?>
        <p><?= htmlspecialchars($m) ?></p>
    <?php endforeach; ?>
</div>
<?php endif; ?>

<?php if ($processado): ?>
<div class="sucesso">
    <p><strong>Processamento concluído!</strong></p>
    <p>Os resultados serão enviados para o e-mail do requisitante.</p>
</div>
<?php endif; ?>

</div>

<script>
document.querySelector("form").addEventListener("submit", function() {
    document.getElementById("loader").style.display = "block";
    const btn = this.querySelector("button");
    if (btn) btn.disabled = true;
});
</script>

</body>
</html>
