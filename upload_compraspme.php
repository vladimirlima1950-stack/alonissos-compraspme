<?php
session_start();

if (!isset($_SESSION['logado']) || $_SESSION['logado'] !== true) {
    header("Location: login.php");
    exit;
}

$cliente           = $_SESSION['usuario'] ?? 'Desconhecido';
$emailCliente      = $_SESSION['email']   ?? '';
$nomeClienteTela   = $_SESSION['nome_cliente'] ?? $cliente;

/* ============================================================
   URL CORRETA DO RAILWAY (ATUALIZADA)
============================================================ */
$railway_base = "https://gregarious-endurance-production-105a.up.railway.app";

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
            'status'   => 'erro',
            'mensagem' => "Erro ao enviar '$campo': $erroCurl"
        ];
    }

    $json = json_decode($resposta, true);

    if (!$json || !isset($json['status'])) {
        return [
            'status'   => 'erro',
            'mensagem' => "Resposta inválida do servidor para '$campo': " . htmlspecialchars($resposta)
        ];
    }

    return $json;
}

/* ============================================================
   Processamento do formulário
============================================================ */
$mensagens  = [];
$processado = false;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {

    /* ============================================================
       ENVIO DOS ARQUIVOS PARA OS NOVOS ENDPOINTS DO main.py
    ============================================================ */

    $respPedidos   = enviarArquivoPME("pedidos",   "upload_pedidos",   $railway_base);
    $mensagens[]   = "Pedidos: "   . ($respPedidos['mensagem'] ?? '');

    $respEntregas  = enviarArquivoPME("entregas",  "upload_entregas",  $railway_base);
    $mensagens[]   = "Entregas: "  . ($respEntregas['mensagem'] ?? '');

    $respLeadtime  = enviarArquivoPME("leadtime",  "upload_leadtime",  $railway_base);
    $mensagens[]   = "Leadtime: "  . ($respLeadtime['mensagem'] ?? '');

    $okPedidos   = isset($respPedidos['status'])  && $respPedidos['status']  === 'ok';
    $okEntregas  = isset($respEntregas['status']) && $respEntregas['status'] === 'ok';
    $okLeadtime  = isset($respLeadtime['status']) && $respLeadtime['status'] === 'ok';

    if ($okPedidos && $okEntregas && $okLeadtime) {

        /* ============================================================
           CHAMADA DO PROCESSAMENTO PME NO RAILWAY
        ============================================================ */

        $curl = curl_init();
        curl_setopt_array($curl, [
            CURLOPT_URL            => "$railway_base/processar_compraspme?email=$emailCliente",
            CURLOPT_RETURNTRANSFER => false,
            CURLOPT_TIMEOUT        => 5
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
<title>Envio de Arquivos Compras PME - MUPE Consultoria</title>

<style>
/* (todo o CSS permanece igual ao original) */
</style>
</head>

<body>
<div class="container">

<h2>Envio de Arquivos Compras PME</h2>
<p>Cliente identificado: <strong><?= htmlspecialchars($nomeClienteTela) ?></strong></p>

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
            • pedido<br>
            • data do pedido<br>
            • produto<br>
            • fornecedor<br>
            • data desejada<br>
            • quantidade pedida
        </p>
        <input type="file" name="pedidos" required>
    </div>

    <!-- BLOCO ENTREGAS -->
    <div class="bloco">
        <h3>Arquivo de Entregas (.csv)</h3>
        <p>
            Colunas:<br>
            • pedido<br>
            • produto<br>
            • fornecedor<br>
            • quantidade entregue<br>
            • data da nota fiscal
        </p>
        <input type="file" name="entregas" required>
    </div>

    <!-- BLOCO LEADTIME -->
    <div class="bloco">
        <h3>Arquivo de Leadtime (.csv)</h3>
        <p>
            Colunas:<br>
            • fornecedor<br>
            • produto<br>
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
