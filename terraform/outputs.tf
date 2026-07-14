output "function_name" {
  description = "Nome da PagamentoFunction."
  value       = aws_lambda_function.pagamento.function_name
}

output "function_arn" {
  description = "ARN da PagamentoFunction."
  value       = aws_lambda_function.pagamento.arn
}

output "webhook_endpoint" {
  description = "URL publica do endpoint de webhook do Mercado Pago."
  value       = "${aws_apigatewayv2_stage.default.invoke_url}/api/webhooks/mercadopago"
}
