from src.infrastructure.handlers.sqs_handler import lambda_handler as _sqs_lambda_handler
from src.infrastructure.handlers.webhook_handler import lambda_handler as _webhook_lambda_handler


def lambda_handler(event, context):
    """
    Entry point único da PagamentoFunction (template.yaml), com dois
    gatilhos possíveis: a fila SQS 'sqs-pagamento-solicitar' e o webhook do
    Mercado Pago via API Gateway.

    Eventos de fila SQS sempre trazem a chave 'Records'; eventos de API
    Gateway (REST ou HTTP API) nunca trazem essa chave — critério simples e
    suficiente para despachar para o handler correto.
    """
    if "Records" in event:
        return _sqs_lambda_handler(event, context)
    return _webhook_lambda_handler(event, context)
