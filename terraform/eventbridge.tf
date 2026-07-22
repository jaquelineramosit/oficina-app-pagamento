resource "aws_cloudwatch_event_rule" "poll_payment_status" {

  name = "oficina-pagamento-poll-status"

  description = "Aciona periodicamente a lambda oficina-pagamento para consultar (GET) o status das orders Pix pendentes na Orders API do Mercado Pago."

  schedule_expression = var.poll_schedule_expression

  state = var.poll_enabled ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "poll_payment_status" {

  rule = aws_cloudwatch_event_rule.poll_payment_status.name

  arn = aws_lambda_function.pagamento.arn
}

resource "aws_lambda_permission" "eventbridge" {

  statement_id = "AllowEventBridgeInvoke"

  action = "lambda:InvokeFunction"

  function_name = aws_lambda_function.pagamento.function_name

  principal = "events.amazonaws.com"

  source_arn = aws_cloudwatch_event_rule.poll_payment_status.arn
}
