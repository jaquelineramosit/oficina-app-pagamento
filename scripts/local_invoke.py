"""
Invoca a PagamentoFunction localmente, em processo (sem SAM/Docker), lendo
um evento de exemplo em `events/`. Útil para iterar rápido contra o
LocalStack: configure AWS_ENDPOINT_URL + as demais variáveis de ambiente
(ver README.md, seção "Testando contra o LocalStack") e rode:

    python scripts/local_invoke.py
    python scripts/local_invoke.py events/webhook_event.json
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.handlers.payment_handler import lambda_handler  # noqa: E402


def main() -> None:
    event_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "events" / "sqs_event.json"
    event = json.loads(event_path.read_text(encoding="utf-8"))

    print(f"Invocando payment_handler.lambda_handler com {event_path}...")
    result = lambda_handler(event, context=None)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
