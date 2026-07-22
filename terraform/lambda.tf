resource "aws_lambda_function" "pagamento" {

  function_name = "oficina-pagamento"

  filename         = "${path.module}/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/lambda.zip")

  role    = var.lab_role_arn
  handler = "src.infrastructure.handlers.payment_handler.lambda_handler"
  runtime = "python3.12"

  timeout     = 15
  memory_size = 256

  environment {

    variables = {

      MP_ACCESS_TOKEN = var.mp_access_token
      MP_API_BASE_URL = var.mp_api_base_url

      ORDERS_TABLE_NAME = var.orders_table_name

      SQS_PAGAMENTO_EFETUADO_QUEUE_URL = var.efetuado_queue_url
      SQS_PAGAMENTO_RECUSADO_QUEUE_URL = var.recusado_queue_url
      SQS_PAGAMENTO_SOLICITAR_DLQ_URL  = var.solicitar_dlq_queue_url

    }
  }

  tags = {
    Name = "oficina-pagamento"
  }
}