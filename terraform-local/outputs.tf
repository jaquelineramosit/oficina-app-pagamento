output "function_name" {
  description = "Nome da Lambda publicada no LocalStack."
  value       = aws_lambda_function.pagamento.function_name
}

output "function_arn" {
  description = "ARN da Lambda publicada no LocalStack."
  value       = aws_lambda_function.pagamento.arn
}
