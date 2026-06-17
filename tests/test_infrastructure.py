import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InfrastructureTests(unittest.TestCase):
    def test_project_declares_fastapi_auth_database_dependencies(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = "\n".join(project["project"].get("dependencies", []))

        self.assertIn("fastapi", dependencies)
        self.assertIn("uvicorn[standard]", dependencies)
        self.assertIn("psycopg[binary]", dependencies)
        self.assertIn("httpx", dependencies)
        self.assertIn("redis", dependencies)
        self.assertIn("rq", dependencies)

    def test_project_configures_ruff_and_pre_commit_linting(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        pre_commit = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

        dev_dependencies = "\n".join(
            project["project"].get("optional-dependencies", {}).get("dev", [])
        )
        self.assertIn("ruff", dev_dependencies)
        self.assertIn("pre-commit", dev_dependencies)
        self.assertEqual(project["tool"]["ruff"]["target-version"], "py311")
        self.assertIn("ruff-check", pre_commit)
        self.assertIn("lint: lint-python", makefile)
        self.assertIn("check: lint test typecheck compile frontend-check", makefile)

    def test_dockerfile_installs_project_and_uses_public_healthcheck(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("pip install --no-cache-dir .", dockerfile)
        self.assertIn("http://127.0.0.1:8765/api/auth/me", dockerfile)
        self.assertNotIn("http://127.0.0.1:8765/api/runs", dockerfile)

    def test_compose_adds_postgres_and_database_url(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("postgres:", compose)
        self.assertIn("image: postgres:16-alpine", compose)
        self.assertIn(
            "DATABASE_URL: postgresql://algo:algo@postgres:5432/algo_trading",
            compose,
        )
        self.assertIn("condition: service_healthy", compose)
        self.assertIn("postgres-data:", compose)
        self.assertIn("MOEX_API_KEY: ${MOEX_API_KEY:-}", compose)
        self.assertIn("MOEXALGO_API_KEY: ${MOEXALGO_API_KEY:-}", compose)
        self.assertIn("MOEX_FUTOI_API_KEY: ${MOEX_FUTOI_API_KEY:-}", compose)

    def test_compose_adds_redis_queue_and_worker(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("redis:", compose)
        self.assertIn("image: redis:7-alpine", compose)
        self.assertIn('"redis-cli", "ping"', compose)
        self.assertIn("redis-data:", compose)
        self.assertIn("worker:", compose)
        self.assertIn("command: python -m algo_trading.worker", compose)
        self.assertIn("REDIS_URL: redis://redis:6379/0", compose)
        self.assertIn('API_RESPONSE_CACHE_ENABLED: "1"', compose)
        self.assertIn('API_CACHE_TTL_LIVE_CHART_SECONDS: "10"', compose)
        self.assertIn("RQ_QUEUE: maintenance", compose)
        self.assertIn("Redis.from_url(os.environ['REDIS_URL']).ping()", compose)
        self.assertIn("condition: service_healthy", compose)

    def test_env_template_is_tracked_while_local_env_is_ignored(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertIn(".env", gitignore.splitlines())
        self.assertIn("MOEX_API_KEY=", env_example)
        self.assertIn("MOEX_FUTOI_API_KEY=", env_example)
        self.assertIn("ADMIN_EMAIL=", env_example)
        self.assertIn("# REDIS_URL=redis://localhost:6379/0", env_example)
        self.assertIn("API_RESPONSE_CACHE_ENABLED=0", env_example)
        self.assertIn("API_CACHE_TTL_MARKET_BREADTH_SECONDS=300", env_example)
        self.assertIn("RQ_QUEUE=maintenance", env_example)
        self.assertIn("HISTORICAL_CSV_RETENTION_DAYS=1095", env_example)
        self.assertIn("HISTORICAL_CSV_REFRESH_SECONDS=3600", env_example)
        self.assertIn("HISTORICAL_CSV_PRUNE_SECONDS=86400", env_example)
        self.assertIn("MOEX_FUTOI_DATA_DIR=historical_data/futoi", env_example)
        self.assertIn("MOEX_FUTOI_RETENTION_DAYS=730", env_example)
        self.assertIn("MOEX_FUTOI_REFRESH_SECONDS=86400", env_example)
        self.assertIn("MOEX_FUTOI_PRUNE_SECONDS=604800", env_example)

    def test_compose_persists_market_breadth_historical_csvs(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

        self.assertIn('user: "${UID:-1000}:${GID:-1000}"', compose)
        self.assertIn("./historical_data:/app/historical_data", compose)
        self.assertIn("MARKET_BREADTH_DATA_DIR: /app/historical_data/breadth", compose)
        self.assertIn('HISTORICAL_DATA_DIR: /app/historical_data', compose)
        self.assertIn('HISTORICAL_CSV_RETENTION_DAYS: "1095"', compose)
        self.assertIn('HISTORICAL_CSV_REFRESH_SECONDS: "3600"', compose)
        self.assertIn('HISTORICAL_CSV_PRUNE_SECONDS: "86400"', compose)
        self.assertIn("MOEX_FUTOI_DATA_DIR: /app/historical_data/futoi", compose)
        self.assertIn('MOEX_FUTOI_RETENTION_DAYS: "730"', compose)
        self.assertIn('MOEX_FUTOI_REFRESH_SECONDS: "86400"', compose)
        self.assertIn('MOEX_FUTOI_PRUNE_SECONDS: "604800"', compose)
        self.assertIn('MARKET_BREADTH_RETENTION_DAYS: "365"', compose)
        self.assertIn("HISTORICAL_DATA_DIR ?= $(CURDIR)/historical_data", makefile)
        self.assertIn('"$(HISTORICAL_DATA_DIR)"', makefile)
        self.assertIn('--user "$$(id -u):$$(id -g)"', makefile)

    def test_compose_persists_error_logs_outside_git(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("./logs:/app/logs", compose)
        self.assertIn("APP_LOG_DIR: /app/logs", compose)
        self.assertIn("LOGS_DIR ?= $(CURDIR)/logs", makefile)
        self.assertIn('"$(LOGS_DIR):/app/logs"', makefile)
        self.assertIn("logs/", gitignore.splitlines())

    def test_docker_smoke_authenticates_before_protected_api_checks(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

        self.assertIn("/api/auth/login", makefile)
        self.assertIn("cuiyeqing960904@gmail.com", makefile)
        self.assertIn('-c "$$cookie_jar"', makefile)
        self.assertIn('-b "$$cookie_jar"', makefile)
        self.assertIn("/api/strategies", makefile)
        self.assertIn("/breadth", makefile)
        self.assertNotIn("/lab", makefile)
