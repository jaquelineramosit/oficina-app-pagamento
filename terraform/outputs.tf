output "lambda_name" {
  value = aws_lambda_function.pagamento.function_name
}

output "lambda_arn" {
  value = aws_lambda_function.pagamento.arn
}

output "api_url" {
  value = aws_apigatewayv2_stage.default.invoke_url
}