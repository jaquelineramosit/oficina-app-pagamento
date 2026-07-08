import os


class Settings:
    """
    Centraliza a leitura de variáveis de ambiente, isolando o resto da
    aplicação de detalhes de configuração de infraestrutura.

    As propriedades leem `os.environ` a cada acesso (em vez de capturar os
    valores como atributos de classe na importação do módulo) para que a
    configuração reflita sempre o ambiente atual — essencial em testes, que
    usam `unittest.mock.patch.dict("os.environ", ...)` para simular
    variáveis diferentes a cada caso.
    """

    @property
    def MP_ACCESS_TOKEN(self) -> str:
        return os.environ.get("MP_ACCESS_TOKEN", "")

    @property
    def MP_WEBHOOK_SECRET(self) -> str:
        return os.environ.get("MP_WEBHOOK_SECRET", "")

    @property
    def MP_API_BASE_URL(self) -> str:
        return os.environ.get("MP_API_BASE_URL", "https://api.mercadopago.com")

    @property
    def ORDERS_TABLE_NAME(self) -> str:
        return os.environ.get("ORDERS_TABLE_NAME", "orders")

    @property
    def RETORNO_PAGAMENTO_QUEUE_URL(self) -> str:
        return os.environ.get("RETORNO_PAGAMENTO_QUEUE_URL", "")

    @property
    def HTTP_TIMEOUT_SECONDS(self) -> float:
        return float(os.environ.get("MP_HTTP_TIMEOUT_SECONDS", "10"))

    @property
    def AWS_REGION(self) -> str:
        return os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

    def validate(self) -> None:
        missing = []
        if not self.MP_ACCESS_TOKEN:
            missing.append("MP_ACCESS_TOKEN")
        if missing:
            raise RuntimeError(
                f"Variáveis de ambiente obrigatórias ausentes: {', '.join(missing)}"
            )


settings = Settings()
