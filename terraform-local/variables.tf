variable "lambda_role_arn" {
  description = "ARN de execution role para a Lambda no LocalStack. Nao precisa existir de verdade: o LocalStack Community nao aplica IAM, so exige que o campo esteja preenchido."
  type        = string
  default     = "arn:aws:iam::000000000000:role/lambda-local-role"
}

variable "mp_access_token" {
  description = "Access Token do Mercado Pago (sandbox) usado nos testes locais."
  type        = string
  default     = "TEST-xxxxxxx"
}

variable "mp_webhook_secret" {
  description = "Secret do webhook do Mercado Pago. Vazio pula a validacao de assinatura."
  type        = string
  default     = ""
}

variable "mp_api_base_url" {
  description = "URL base da API do Mercado Pago."
  type        = string
  default     = "https://api.mercadopago.com"
}

variable "orders_table_name" {
  description = "Nome da tabela DynamoDB orders, ja criada no LocalStack pelo terraform-local do oficina-infra-pagamento."
  type        = string
  default     = "orders"
}

variable "solicitar_queue_name" {
  description = "Nome da fila sqs-pagamento-solicitar, ja criada no LocalStack pelo terraform-local do oficina-infra-pagamento."
  type        = string
  default     = "sqs-pagamento-solicitar"
}

variable "efetuado_queue_name" {
  description = "Nome da fila sqs-pagamento-efetuado, ja criada no LocalStack pelo terraform-local do oficina-infra-pagamento."
  type        = string
  default     = "sqs-pagamento-efetuado"
}

variable "recusado_queue_name" {
  description = "Nome da fila sqs-pagamento-recusado, ja criada no LocalStack pelo terraform-local do oficina-infra-pagamento."
  type        = string
  default     = "sqs-pagamento-recusado"
}
