<?php
session_start();

if (!isset($_SESSION['logado']) || $_SESSION['logado'] !== true) {
    header("Location: login.php");
    exit;
}

# IMPORTANTE:
# $cliente continua sendo o identificador usado internamente (número)
# $nomeClienteTela é apenas para exibição na página

$cliente           = $_SESSION['usuario'] ?? 'Desconhecido';   // usado internamente
$emailCliente      = $_SESSION['email']   ?? '';
$nomeClienteTela   = $_SESSION['nome_cliente'] ?? $cliente;     // usado apenas na tela

$railway_base = "https://cozy-vision-production-6526.up.railway.app";

function enviarArquivoOTIF($campo, $endpoint, $railway_base) {
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

$mensagens  = [];
$processado = false;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {

    $respPedidos = enviarArquivoOTIF("pedidos", "upload_pedidos", $railway_base);
    $mensagens[] = "Pedidos: " . ($respPedidos['mensagem'] ?? '');

    $respFaturamentos = enviarArquivoOTIF("faturamentos", "upload_faturamentos", $railway_base);
    $mensagens[] = "Faturamentos: " . ($respFaturamentos['mensagem'] ?? '');

    $pedidosOK      = isset($respPedidos['status'])      && $respPedidos['status']      === 'ok';
    $faturamentosOK = isset($respFaturamentos['status']) && $respFaturamentos['status'] === 'ok';

    if ($pedidosOK && $faturamentosOK) {

        $curl = curl_init();
        curl_setopt_array($curl, [
            CURLOPT_URL            => "$railway_base/processar_otif?email=$emailCliente",
            CURLOPT_RETURNTRANSFER => false,
            CURLOPT_TIMEOUT        => 5
        ]);
        curl_exec($curl);
        curl_close($curl);

        $mensagens[] = "Processamento iniciado. Você receberá o resultado por e‑mail.";
        $processado  = true;

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
    max-width: 900px;
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
.form-grid {
    display: flex;
    gap: 25px;
    margin-top: 25px;
}
.bloco {
    flex: 1;
    background: #f9fafb;
    padding: 20px;
    border-radius: 8px;
    border-left: 4px solid #2563eb;
}
.bloco h3 {
    margin-top: 0;
    color: #374151;
}
.bloco p {
    font-size: 14px;
    color: #374151;
    margin-bottom: 12px;
}
input[type="file"] {
    margin-top: 12px;
    padding: 10px;
    background: #eef2ff;
    border: 2px solid #6366f1;
    border-radius: 6px;
    font-size: 14px;
    cursor: pointer;
}
input[type="file"]:hover {
    background: #e0e7ff;
    border-color: #4f46e5;
}
button {
    width: 100%;
    padding: 16px;
    background: #1e40af;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    font-size: 17px;
    font-weight: bold;
    cursor: pointer;
    margin-top: 30px;
    box-shadow: 0 4px 10px rgba(0,0,0,0.15);
    transition: all 0.25s ease;
}
button:hover {
    background: #1d4ed8;
    transform: translateY(-2px);
    box-shadow: 0 6px 14px rgba(0,0,0,0.22);
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
</style>
</head>

<body>
<div class="container">

<h2>Envio de Arquivos OTIF</h2>
<p>Cliente identificado: <strong><?= htmlspecialchars($nomeClienteTela) ?></strong></p>

<div id="loader">
    <div class="spinner"></div>
    <p>Enviando arquivos... Aguarde.</p>
</div>

<form method="POST" enctype="multipart/form-data">

<div class="form-grid">

    <!-- BLOCO PEDIDOS -->
    <div class="bloco">
        <h3>Arquivo de Pedidos (.csv)</h3>
        <p>
            O arquivo de Pedidos deve conter:<br><br>
            1) Número da ordem (1ª coluna);<br>
            2) Identificação do cliente (2ª coluna);<br>
            3) Data desejada (DD/MM/AAAA) — 3ª coluna;<br>
            4) SKU / item / peça (4ª coluna);<br>
            5) Quantidade pedida (5ª coluna).<br><br>
            Todas as colunas, <strong>exceto a terceira</strong>, devem ser texto.<br>
            O arquivo deve ser salvo como <strong>.csv</strong>.
        </p>
        <input type="file" name="pedidos" required>
    </div>

    <!-- BLOCO FATURAMENTOS -->
    <div class="bloco">
        <h3>Arquivo de Faturamentos (.csv)</h3>
        <p>
            O arquivo de Faturamentos deve conter:<br><br>
            1) Data do faturamento (DD/MM/AAAA) — 1ª coluna;<br>
            2) Identificação do cliente (2ª coluna);<br>
            3) SKU / item / peça (3ª coluna);<br>
            4) Quantidade faturada (4ª coluna);<br>
            5) Ordem de venda (5ª coluna).<br><br>
            Todas as colunas, <strong>exceto a primeira</strong>, devem ser texto.<br>
            O arquivo deve ser salvo como <strong>.csv</strong>.
        </p>
        <input type="file" name="faturamentos" required>
    </div>

</div>

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
