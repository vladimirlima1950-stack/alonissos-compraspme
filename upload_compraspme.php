<?php
session_start();

if (!isset($_SESSION['logado']) || $_SESSION['logado'] !== true) {
    header("Location: login.php");
    exit;
}

$cliente         = $_SESSION['usuario'] ?? 'Desconhecido';
$emailCliente    = $_SESSION['email']   ?? '';
$nomeClienteTela = $_SESSION['nome'] ?? $cliente;


/* ============================================================
   URL CORRETA DO RAILWAY
============================================================ */
$railway_base = "https://alonissos-compraspme-production.up.railway.app";

/* ============================================================
   Função genérica para enviar qualquer arquivo CSV ao Railway
============================================================ */
function enviarArquivoPME($campo, $endpoint, $railway_base) {

    if (!isset($_FILES[$campo]) || $_FILES[$campo]['error'] !== UPLOAD_ERR_OK) {
        return [
            'status'   => 'erro',
            'mensagem' => "Arquivo '$campo' não enviado ou erro no upload."
        ];
    }

    $arquivo = $_FILES[$campo];
    $ext = strtolower(pathinfo($arquivo['name'], PATHINFO_EXTENSION));

    if ($ext !== "csv") {
        return [
            'status'   => 'erro',
            'mensagem' => "Erro: o arquivo '$campo' deve ser .csv"
        ];
    }

    $mime = mime_content_type($arquivo['tmp_name']);
    if ($mime !== "text/plain" && $mime !== "text/csv" && $mime !== "application/vnd.ms-excel") {
        return [
            'status'   => 'erro',
            'mensagem' => "Erro: o arquivo '$campo' não parece ser um CSV válido (MIME: $mime)."
        ];
    }

    $nomeSeguro = basename($arquivo['name']);
    $urlFinal   = rtrim($railway_base, '/') . '/' . ltrim($endpoint, '/');

    $curl = curl_init();
    curl_setopt_array($curl, [
        CURLOPT_URL            => $urlFinal,
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
            'status'   => 'erro',
            'mensagem' => "Erro cURL ao enviar '$campo': $erroCurl"
        ];
    }

    $json = json_decode($resposta, true);

    if (!$json) {
        return [
            'status'   => 'erro',
            'mensagem' => "Resposta inválida do servidor para '$campo': " . htmlspecialchars($resposta)
        ];
    }

    $mensagemRetorno   = $json['mensagem'] ?? $json['detail'] ?? $resposta;
    $statusNormalizado = (isset($json['status']) && in_array(strtolower($json['status']), ['ok', 'sucesso'])) ? 'ok' : 'erro';

    return [
        'status'   => $statusNormalizado,
        'mensagem' => $mensagemRetorno
    ];
}

/* ============================================================
   Processamento do formulário
============================================================ */
$mensagens  = [];
$processado = false;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {

    $respPedidos   = enviarArquivoPME("pedidos",   "upload_pedidos",   $railway_base);
    $mensagens[]   = "Pedidos: "   . ($respPedidos['mensagem'] ?? '');

    $respEntregas  = enviarArquivoPME("entregas",  "upload_entregas",  $railway_base);
    $mensagens[]   = "Entregas: "  . ($respEntregas['mensagem'] ?? '');

    $respLeadtime  = enviarArquivoPME("leadtime",  "upload_leadtime",  $railway_base);
    $mensagens[]   = "Leadtime: "  . ($respLeadtime['mensagem'] ?? '');

    $okPedidos   = ($respPedidos['status']  === 'ok');
    $okEntregas  = ($respEntregas['status'] === 'ok');
    $okLeadtime  = ($respLeadtime['status'] === 'ok');

    if ($okPedidos && $okEntregas && $okLeadtime) {

        $urlProcessar = rtrim($railway_base, '/') . "/processar_compraspme?email=" . urlencode($emailCliente);

        $curl = curl_init();
        curl_setopt_array($curl, [
            CURLOPT_URL            => $urlProcessar,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 10
        ]);
        curl_exec($curl);
        curl_close($curl);

        $mensagens[] = "Processamento iniciado. Você receberá o resultado por e‑mail.";
        $processado  = true;

    } else {
        $mensagens[] = "Processamento não iniciado: um ou mais arquivos apresentaram erro.";
    }
}
?>
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Envio de Arquivos Compras PME - MUPE Consultoria</title>



<style>
:root {
    --primary-color: #0d47a1;
    --primary-hover: #1565c0;
    --bg-color: #f4f6f9;
    --card-bg: #ffffff;
    --text-color: #333333;
    --border-color: #e0e0e0;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background-color: var(--bg-color);
    color: var(--text-color);
    margin: 0;
    padding: 40px 20px;
    display: flex;
    justify-content: center;
}

.container {
    width: 100%;
    max-width: 900px;
    background-color: var(--card-bg);
    padding: 30px;
    border-radius: 12px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08);
}

h2 {
    color: var(--primary-color);
    margin-top: 0;
    font-size: 24px;
    text-align: center;
}

.cliente-info {
    text-align: center;
    margin-bottom: 25px;
    color: #555;
}

.grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 20px;
}

.bloco {
    background: #fafafa;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 18px;
}

.bloco h3 {
    margin-top: 0;
    margin-bottom: 8px;
    font-size: 16px;
    color: #1a237e;
}

.bloco p {
    font-size: 13px;
    color: #666;
    line-height: 1.5;
    margin-bottom: 12px;
}

input[type="file"] {
    width: 100%;
    font-size: 14px;
}

button[type="submit"] {
    width: 100%;
    background-color: var(--primary-color);
    color: #ffffff;
    border: none;
    padding: 14px;
    border-radius: 6px;
    font-size: 16px;
    font-weight: bold;
    cursor: pointer;
    transition: background-color 0.2s ease;
}

button[type="submit"]:hover {
    background-color: var(--primary-hover);
}

.msg {
    background-color: #eef3fc;
    border-left: 4px solid var(--primary-color);
    padding: 12px 16px;
    border-radius: 4px;
    margin-top: 20px;
    font-size: 14px;
}

.sucesso {
    background-color: #e8f5e9;
    border-left: 4px solid #2e7d32;
    padding: 12px 16px;
    border-radius: 4px;
    margin-top: 20px;
    color: #1b5e20;
}

.botao-voltar {
    display: block;
    text-align: center;
    margin-top: 20px;
    color: var(--primary-color);
    text-decoration: none;
    font-weight: bold;
}

.botao-voltar:hover {
    text-decoration: underline;
}

#loader {
    display: none;
    text-align: center;
    margin-bottom: 20px;
}

.spinner {
    border: 4px solid #f3f3f3;
    border-top: 4px solid var(--primary-color);
    border-radius: 50%;
    width: 32px;
    height: 32px;
    animation: spin 1s linear infinite;
    margin: 0 auto 10px auto;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
</style>

</head>

<body>
<div class="container">

<h2>Envio de Arquivos Compras PME</h2>
<p class="cliente-info">Cliente identificado: <strong><?= htmlspecialchars($nomeClienteTela) ?></strong></p>

<div id="loader">
    <div class="spinner"></div>
    <p>Enviando arquivos... Aguarde.</p>
</div>

<form method="POST" enctype="multipart/form-data">

    <!-- BLOCO PEDIDOS -->
    <div class="bloco">
        <h3>Arquivo de Pedidos (.csv)</h3>
        <p>
            Colunas:<br>
            • pedido número<br>
            • data do pedido DD/MM/AAAA<br>
            • produto/material/artigo/sku<br>
            • fornecedor código<br>
            • data desejada DD/MM/AAAA<br>
            • quantidade pedida
        </p>
        <input type="file" name="pedidos" required>
    </div>

    <!-- BLOCO ENTREGAS -->
    <div class="bloco">
        <h3>Arquivo de Entregas (.csv)</h3>
        <p>
            Colunas:<br>
            • pedido número<br>
            • produto/material/artigo/sku<br>
            • fornecedor código<br>
            • quantidade entregue<br>
            • data da nota fiscal DD/MM/AAAA
        </p>
        <input type="file" name="entregas" required>
    </div>

    <!-- BLOCO LEADTIME -->
    <div class="bloco">
        <h3>Arquivo de Leadtime (.csv)</h3>
        <p>
            Colunas:<br>
            • fornecedor código<br>
            • produto/material/artigo/sku<br>
            • leadtime em dias
        </p>
        <input type="file" name="leadtime" required>
    </div>

    <button type="submit">Enviar arquivos e processar Compras PME</button>

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
    <p><strong>Processamento iniciado!</strong></p>
    <p>O resultado será enviado para o e‑mail cadastrado.</p>
</div>
<a href="https://mupeconsult.com/" class="botao-voltar">Voltar ao site MUPE Consultoria</a>
<?php endif; ?>

</div>

<script>
document.querySelector("form").addEventListener("submit", function() {
    document.getElementById("loader").style.display = "block";
});
</script>

</body>
</html>
