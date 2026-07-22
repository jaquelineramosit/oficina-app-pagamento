output "lambda_name" {
  value = aws_lambda_function.pagamento.function_name
}

output "lambda_arn" {
  value = aws_lambda_function.pagamento.arn
}