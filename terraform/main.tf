locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ---------------------------------------------------------------------
# Empacotamento: instala as dependencias de requirements.txt e copia o
# codigo fonte (src/) para build/, depois zipa. Substitui o "sam build".
# ---------------------------------------------------------------------
resource "null_resource" "lambda_package" {
  triggers = {
    requirements_hash = filemd5("${path.module}/../requirements.txt")
    source_hash       = sha1(join("", [for f in fileset("${path.module}/../src", "**") : filesha1("${path.module}/../src/${f}")]))
  }

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      rm -rf "${path.module}/build"
      mkdir -p "${path.module}/build"
      pip install -r "${path.module}/../requirements.txt" -t "${path.module}/build" --quiet
      cp -r "${path.module}/../src" "${path.module}/build/src"
    EOT
  }
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/build"
  output_path = "${path.module}/build.zip"

  depends_on = [null_resource.lambda_package]
}

# ---------------------------------------------------------------------
# Lambda unica do dominio de pagamento (2 gatilhos: SQS + webhook via
# API Gateway), usando a LabRole da AWS Academy como execution role.
# ---------------------------------------------------------------------
resource "aws_lambda_function" "pagamento" {
  function_name = "oficina-pagamento"
  role          = var.lab_role_arn
  handler       = "src.infrastructure.handlers.payment_handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = 15
  memory_size   = 256

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      MP_ACCESS_TOKEN                  = var.mp_access_token
      MP_WEBHOOK_SECRET                = var.mp_webhook_secret
      MP_API_BASE_URL                  = var.mp_api_base_url
      ORDERS_TABLE_NAME                = var.orders_table_name
      SQS_PAGAMENTO_EFETUADO_QUEUE_URL = var.efetuado_queue_url
      SQS_PAGAMENTO_RECUSADO_QUEUE_URL = var.recusado_queue_url
      SQS_PAGAMENTO_SOLICITAR_DLQ_URL  = var.solicitar_dlq_queue_url
    }
  }

  tags = merge(local.common_tags, { Name = "oficina-pagamento" })
}

# ---------------------------------------------------------------------
# Gatilho 1: fila sqs-pagamento-solicitar (criada no oficina-pagamento-infras)
# ---------------------------------------------------------------------
resource "aws_lambda_event_source_mapping" "solicitar" {
  event_source_arn = var.solicitar_queue_arn
  function_name    = aws_lambda_function.pagamento.arn
  batch_size       = 10

  function_response_types = ["ReportBatchItemFailures"]
}

# ---------------------------------------------------------------------
# Gatilho 2: webhook do Mercado Pago via API Gateway HTTP API
# ---------------------------------------------------------------------
resource "aws_apigatewayv2_api" "webhook" {
  name          = "oficina-pagamento-webhook"
  protocol_type = "HTTP"

  tags = local.common_tags
}

resource "aws_apigatewayv2_integration" "webhook" {
  api_id                 = aws_apigatewayv2_api.webhook.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.pagamento.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "webhook" {
  api_id    = aws_apigatewayv2_api.webhook.id
  route_key = "POST /api/webhooks/mercadopago"
  target    = "integrations/${aws_apigatewayv2_integration.webhook.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.webhook.id
  name        = "$default"
  auto_deploy = true

  tags = local.common_tags
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.pagamento.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.webhook.execution_arn}/*/*"
}
