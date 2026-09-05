<?php
session_start();

if (!isset($_SESSION['logado']) || $_SESSION['logado'] !== true) {
    header("Location: login.php");
    exit;
}

$cliente      = $_SESSION['usuario'] ?? 'Desconhecido';
$emailCliente = $_SESSION['email']   ?? '';
$railway_base = "https://cozy-vision-production-6526.up.railway.app";

function enviarArquivoOTIF($campo, $endpoint, $railway_base) {
    if (!isset($_FILES[$campo]) || $_FILES[$campo]['error'] !== UPLOAD_ERR_OK) {
        return [
            'status'   => 'erro',
            'mensagem' => "Arquivo '$campo' não enviado ou erro no upload."
        ];
    }

    $arquivo = $_FILES[$campo];

    // Extensão
    $ext = strtolower(pathinfo($arquivo['name'], PATHINFO_EXTENSION));
    if ($ext !== "csv") {
        return [
            'status'   => 'erro',
            'mensagem' => "Erro: o arquivo '$campo' deve ser .csv"
        ];
    }

    // MIME básico
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

$mensagens  = [];
$processado = false;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {

    // Envia pedidos
    $respPedidos = enviarArquivoOTIF("pedidos", "upload_pedidos", $railway_base);
    $mensagens[] = "Pedidos: " . ($respPedidos['mensagem'] ?? '');

    // Envia faturamentos
    $respFaturamentos = enviarArquivoOTIF("faturamentos", "upload_faturamentos", $railway_base);
    $mensagens[] = "Faturamentos: " . ($respFaturamentos['mensagem'] ?? '');

    $pedidosOK      = isset($respPedidos['status'])      && $respPedidos['status']      === 'ok';
    $faturamentosOK = isset($respFaturamentos['status']) && $respFaturamentos['status'] === 'ok';

    if ($pedidosOK && $faturamentosOK) {

        // Chama processamento OTIF
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
            $jsonProc = json_decode($respostaProcessamento, true);

            if ($jsonProc && isset($jsonProc['status']) && $jsonProc['status'] === 'processado') {
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
.botao-voltar {
    display: inline-block;
    margin-top: 20px;
    padding: 12px 20px;
    background: #2563eb;
    color: white;
    border-radius: 6px;
    text-decoration: none;
    font-size: 15px;
}
.botao-voltar:hover {
    background: #1d4ed8;
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
.instrucao {
    background: #f9fafb;
    padding: 10px;
    border-left: 4px solid #2563eb;
    margin-top: 8px;
    margin-bottom: 15px;
    font-size: 14px;
    color: #374151;
    border-radius: 4px;
}
</style>
</head>

<body>
<div class="container">

<h2>Envio de Arquivos OTIF</h2>
<p>Cliente identificado: <strong><?= htmlspecialchars($cliente) ?></strong></p>

<div id="loader">
    <div class="spinner"></div>
    <p>Enviando arquivos... Aguarde.</p>
</div>

<form method="POST" enctype="multipart/form-data">

<h3>Arquivo de Pedidos (.csv)</h3>
<div class="instrucao">
    Deve conter 5 colunas:<br>
    1) Número da ordem<br>
    2) Cliente<br>
    3) Data desejada (DD/MM/AAAA)<br>
    4) SKU<br>
    5) Quantidade pedida
</div>
<input type="file" name="pedidos" required>

<h3>Arquivo de Faturamentos (.csv)</h3>
<div class="instrucao">
    Deve conter 5 colunas:<br>
    1) Data do faturamento (DD/MM/AAAA)<br>
    2) Cliente<br>
    3) SKU<br>
    4) Quantidade faturada<br>
    5) Ordem de venda
</div>
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
