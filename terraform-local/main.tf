# Le as filas ja criadas no LocalStack pelo terraform-local do
# oficina-infra-pagamento (precisa rodar `terraform apply` la primeiro).
data "aws_sqs_queue" "solicitar" {
  name = var.solicitar_queue_name
}

data "aws_sqs_queue" "efetuado" {
  name = var.efetuado_queue_name
}

data "aws_sqs_queue" "recusado" {
  name = var.recusado_queue_name
}

# ---------------------------------------------------------------------
# Empacotamento: mesmo esquema do terraform/ real (instala
# requirements.txt + copia src/ em build/, depois zipa).
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
# Lambda publicada de verdade no LocalStack (nao so invocada em processo
# como o scripts/local_invoke.py), com o gatilho SQS ativo.
# ---------------------------------------------------------------------
resource "aws_lambda_function" "pagamento" {
  function_name = "oficina-pagamento"
  role          = var.lambda_role_arn
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
      SQS_PAGAMENTO_EFETUADO_QUEUE_URL = data.aws_sqs_queue.efetuado.url
      SQS_PAGAMENTO_RECUSADO_QUEUE_URL = data.aws_sqs_queue.recusado.url
      AWS_ENDPOINT_URL                 = "http://host.docker.internal:4566"
    }
  }
}

resource "aws_lambda_event_source_mapping" "solicitar" {
  event_source_arn = data.aws_sqs_queue.solicitar.arn
  function_name    = aws_lambda_function.pagamento.arn
  batch_size       = 10

  function_response_types = ["ReportBatchItemFailures"]
}
