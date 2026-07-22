# resources_local — testes locais contra o LocalStack

Scripts Python puros (sem Terraform, sem executor Docker de Lambda) para
exercitar o gatilho SQS da Lambda `oficina-pagamento` localmente, contra uma
instância do [LocalStack](https://www.localstack.cloud/) já provisionada com
as filas/tabela do
[`oficina-pagamento-infras`](https://github.com/jaquelineramosit/oficina-pagamento-infras).

Este diretório substitui o antigo `terraform-local/` (que publicava a Lambda
de verdade no executor Docker do LocalStack): aqui, em vez de publicar a
Lambda, o handler real (`payment_handler.lambda_handler`) é chamado
diretamente em processo, a partir de mensagens lidas de uma fila SQS do
LocalStack.

## Arquivos

| Arquivo | Papel |
|---|---|
| `config.py` | `Settings` (dataclass) — lê `AWS_REGION`, `LOCALSTACK_URL`, `QUEUE_URL`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` de variáveis de ambiente (ou de um `.env` na raiz do projeto, via `python-dotenv`), com defaults apontando pro LocalStack padrão (`http://localhost:4566`). |
| `aws_clients.py` | Cria os clients `boto3` (`sqs`, `dynamodb`) já apontados para `settings.endpoint_url`. |
| `runner.py` (`LocalLambdaRunner`) | Faz long-polling na fila configurada (`QUEUE_URL`), monta um evento SQS (`{"Records": [...]}`) a partir da mensagem recebida e chama o handler informado no construtor. Se a mensagem não vier em `batchItemFailures` no retorno, ela é apagada da fila; caso contrário, permanece para reprocessamento. |
| `local_runner.py` | Ponto de entrada: instancia `LocalLambdaRunner` com `payment_handler.lambda_handler` (o handler de verdade da Lambda) e roda em loop infinito. |
| `send_message.py` | Publica uma mensagem de exemplo (payload de criação de order Pix) na fila configurada — usado para disparar o runner acima. |
| `test_connection.py` | Sanity check: lista as filas SQS e tabelas DynamoDB visíveis no endpoint configurado, para confirmar que a conexão com o LocalStack está OK antes de rodar o restante. |
| `sample_event.json` | Evento de exemplo (`Records: [...]`) mantido como referência; não é lido por nenhum script atualmente. |

## Pré-requisitos

- LocalStack rodando, com as filas (`sqs-pagamento-solicitar`, etc.) e a
  tabela DynamoDB já criadas pelo `oficina-pagamento-infras` (veja o README
  daquele repositório).
- Dependências instaladas a partir da **raiz do projeto**:

  ```bash
  pip install -r requirements-dev.txt
  ```

  (`boto3` e `python-dotenv` já estão declarados ali.)

## Configuração (opcional)

Crie um `.env` na raiz do projeto se quiser sobrescrever os defaults:

```
AWS_REGION=us-east-1
LOCALSTACK_URL=http://localhost:4566
QUEUE_URL=http://localhost:4566/000000000000/sqs-pagamento-solicitar
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
```

Sem `.env`, esses mesmos valores já são os defaults em `config.py`.

## Uso

Todos os comandos abaixo devem ser executados **a partir da raiz do
repositório** (não de dentro de `resources_local/`), como módulos do pacote
`resources_local`:

1. Confirme a conectividade com o LocalStack:

   ```bash
   python -m resources_local.test_connection
   ```

2. Em um terminal, suba o runner (fica em loop, dando long-poll na fila):

   ```bash
   python -m resources_local.local_runner
   ```

3. Em outro terminal, publique uma mensagem de teste:

   ```bash
   python -m resources_local.send_message
   ```

   O runner do passo 2 deve logar o recebimento da mensagem, processá-la
   através do `payment_handler.lambda_handler` real (criando a Order no
   sandbox do Mercado Pago e persistindo o resultado no DynamoDB do
   LocalStack) e apagar a mensagem da fila se o processamento tiver sucesso.

Para conferir o resultado, use o AWS CLI apontado para o LocalStack, como
descrito no README principal do projeto (seção "Testando contra o
LocalStack").
