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

    def test_docker_smoke_authenticates_before_protected_api_checks(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

        self.assertIn("/api/auth/register", makefile)
        self.assertIn('-c "$$cookie_jar"', makefile)
        self.assertIn('-b "$$cookie_jar"', makefile)
        self.assertIn("/api/strategies", makefile)
