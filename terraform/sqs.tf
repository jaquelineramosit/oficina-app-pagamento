resource "aws_lambda_event_source_mapping" "solicitar" {

  event_source_arn = var.solicitar_queue_arn

  function_name = aws_lambda_function.pagamento.arn

  batch_size = 10

  function_response_types = [
    "ReportBatchItemFailures"
  ]
}