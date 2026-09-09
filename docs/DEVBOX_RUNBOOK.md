# Trade_Bot - DevBox Linux Runbook

Este guia permite clonar o repositório em uma DevBox nova e reproduzir o ambiente do zero.

## 1. Instalação e Preparação do Ambiente (Flutter & Android)
Instale o SDK do Flutter e do Android de forma isolada e local para o projeto:

```bash
./scripts/install-flutter.sh
./scripts/install-android-sdk.sh
source ./scripts/use-android.sh
```

**Verificação de Sucesso:**
1. Confirme se as ferramentas estão corretas:
   ```bash
   flutter --version
   ```
   *(Deve retornar `Flutter 3.44.7` e `Dart 3.12.2`)*
2. Confirme os componentes do Android:
   ```bash
   sdkmanager --list_installed
   ```
   *(Deve listar `platform-tools`, `platforms;android-36`, `build-tools;36.0.0`, e `ndk;28.2.13676358`)*

## 2. Banco de Dados e Backend (Python)
Com as ferramentas ativas, suba o banco de dados via Docker e inicie a API FastAPI:

```bash
# Inicie o PostgreSQL
docker compose up -d postgres
# (Opcional) Iniciar postgres isolado para testes
# docker compose --profile test up -d postgres_test

# Sincronize o ambiente Python
uv sync --locked

# Aplique as migrações no banco
uv run alembic upgrade head

# Inicie o Backend localmente apenas na porta 8000
uv run uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log --ws websockets-sansio
```

## 3. Rodando o Aplicativo Mobile (Flutter)
Em um novo terminal (certifique-se de usar `source ./scripts/use-android.sh`), redirecione a porta do emulador/tablet para a sua API local e rode o aplicativo:

```bash
adb reverse tcp:8000 tcp:8000

cd apps/mobile_app
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

## 4. Testes e Validação Contínua (CI Local)
O script de CI nativo para Linux formata, analisa e testa todo o ambiente:

```bash
./scripts/check.sh
```
*(Para incluir os testes de banco, certifique-se de que o `postgres_test` está ativo e execute `./scripts/check.sh --database`)*

---
**🔐 Segurança:** O arquivo `.env` mantém as credenciais e lógica inalteradas, e o backend jamais expõe dados na rede local, restringindo-se a `127.0.0.1`.
