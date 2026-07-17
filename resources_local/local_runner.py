from .runner import LocalLambdaRunner
import logging

from src.infrastructure.handlers.payment_handler import lambda_handler

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.info("Local Lambda Runner iniciado")
runner = LocalLambdaRunner(lambda_handler)

runner.run()
logger.info("Local Lambda Runner finalizando")