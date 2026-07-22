variable "aws_region" {
  description = "Regiao AWS onde os recursos serao criados."
  type        = string

  validation {
    condition     = length(trimspace(var.aws_region)) > 0
    error_message = "aws_region nao pode ser vazio."
  }
}

variable "project_name" {
  description = "Nome do projeto usado em tags."
  type        = string
  default     = "oficina"
}

variable "environment" {
  description = "Ambiente da infraestrutura."
  type        = string
  default     = "dev"
}

variable "lab_role_arn" {
  description = "ARN da LabRole provisionada pela AWS Academy, usada como execution role da Lambda (a Academy nao permite criar roles IAM novas)."
  type        = string
  default     = "arn:aws:iam::550039263173:role/LabRole"
}

variable "mp_access_token" {
  description = "Access Token (ex.: APP_USR-... ou TEST-...) da aplicacao no Mercado Pago."
  type        = string
  sensitive   = true
}

variable "poll_schedule_expression" {
  description = "Expressao de agendamento (rate/cron) do EventBridge que aciona o polling de status das orders pendentes na Orders API do Mercado Pago."
  type        = string
  default     = "rate(1 minute)"
}

variable "solicitar_queue_arn" {
  description = "ARN da fila sqs-pagamento-solicitar (criada no oficina-pagamento-infras), usada para o gatilho SQS da Lambda."
  type        = string

  validation {
    condition     = length(trimspace(var.solicitar_queue_arn)) > 0
    error_message = "solicitar_queue_arn nao pode ser vazio."
  }
}

variable "efetuado_queue_url" {
  description = "URL da fila sqs-pagamento-efetuado (criada no oficina-pagamento-infras), repassada como variavel de ambiente da Lambda."
  type        = string
}

variable "recusado_queue_url" {
  description = "URL da fila sqs-pagamento-recusado (criada no oficina-pagamento-infras), repassada como variavel de ambiente da Lambda."
  type        = string
}

variable "solicitar_dlq_queue_url" {
  description = "URL da DLQ sqs-pagamento-solicitar-dlq (criada no oficina-pagamento-infras), repassada como variavel de ambiente da Lambda. Opcional: enquanto vazia, payloads invalidos (DomainValidationError) nao sao publicados em nenhuma DLQ, so logados."
  type        = string
  default     = ""
}

variable "orders_table_name" {
  description = "Nome da tabela DynamoDB orders (criada no oficina-pagamento-infras), repassada como variavel de ambiente da Lambda."
  type        = string
  default     = "orders"
}

variable "mp_api_base_url" {
  description = "URL base da API do Mercado Pago."
  type        = string
  default     = "https://api.mercadopago.com"
}
