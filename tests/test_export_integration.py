"""Smoke / integration tests for the export feature.

Validates:
- Export router endpoints appear in /openapi.json (Requirement 6.1)
- No imports from src/agents/ or src/core/research_manager in src/export/ (Requirement 6.3)
- EXPORT_DIR and EXPORT_BASE_URL defaults work when env vars are unset (Requirement 5.3)

Requirements: 5.3, 6.1, 6.3
"""

from __future__ import annotations

import ast
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import asyncpg
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_app_client() -> TestClient:
    """Return a TestClient for the full FastAPI app with a mock pool/manager."""
    # Patch DB and ResearchManager so lifespan doesn't need a real DB
    mock_pool = MagicMock(spec=asyncpg.Pool)

    with patch("src.db.pool.init_db", return_value=mock_pool), patch(
        "src.db.pool.close_pool"
    ), patch("src.core.research_manager.ResearchManager"):
        # Import app fresh (may already be imported; that's fine)
        from src.api.main import app

        return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 1. Export endpoints appear in /openapi.json (Requirement 6.1)
# ---------------------------------------------------------------------------


def test_export_markdown_endpoint_in_openapi():
    """GET /api/export/{session_id}/markdown must appear in the OpenAPI schema."""
    client = _get_app_client()
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert (
        "/api/export/{session_id}/markdown" in paths
    ), "Markdown export endpoint not found in /openapi.json"


def test_export_pdf_endpoint_in_openapi():
    """GET /api/export/{session_id}/pdf must appear in the OpenAPI schema."""
    client = _get_app_client()
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert (
        "/api/export/{session_id}/pdf" in paths
    ), "PDF export endpoint not found in /openapi.json"


def test_export_endpoints_have_get_method():
    """Both export endpoints must be registered as GET operations."""
    client = _get_app_client()
    paths = client.get("/openapi.json").json()["paths"]
    assert "get" in paths["/api/export/{session_id}/markdown"]
    assert "get" in paths["/api/export/{session_id}/pdf"]


def test_export_endpoints_have_summary():
    """Both export endpoints must have an OpenAPI summary (Requirement 6.4)."""
    client = _get_app_client()
    paths = client.get("/openapi.json").json()["paths"]
    md_op = paths["/api/export/{session_id}/markdown"]["get"]
    pdf_op = paths["/api/export/{session_id}/pdf"]["get"]
    assert md_op.get("summary"), "Markdown endpoint missing OpenAPI summary"
    assert pdf_op.get("summary"), "PDF endpoint missing OpenAPI summary"


# ---------------------------------------------------------------------------
# 2. No forbidden imports in src/export/ (Requirement 6.3)
# ---------------------------------------------------------------------------

EXPORT_SRC_DIR = Path("src/export")
FORBIDDEN_IMPORT_PREFIXES = (
    "src.agents",
    "src.core.research_manager",
)


def _collect_import_names(tree: ast.AST) -> list[str]:
    """Return all module names imported in an AST."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def _python_files_under(directory: Path):
    return list(directory.rglob("*.py"))


@pytest.mark.parametrize("py_file", _python_files_under(EXPORT_SRC_DIR))
def test_no_forbidden_imports_in_export_package(py_file: Path):
    """src/export/ must not import from src/agents/ or src/core/research_manager."""
    source = py_file.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(py_file))
    imported = _collect_import_names(tree)
    for name in imported:
        for forbidden in FORBIDDEN_IMPORT_PREFIXES:
            assert not name.startswith(
                forbidden
            ), f"{py_file} imports '{name}' which is forbidden in the export package"


# ---------------------------------------------------------------------------
# 3. EXPORT_DIR and EXPORT_BASE_URL defaults (Requirement 5.3)
# ---------------------------------------------------------------------------


def test_export_dir_default_when_env_unset():
    """EXPORT_DIR defaults to './exports' when the env var is not set."""
    env = {k: v for k, v in os.environ.items() if k != "EXPORT_DIR"}
    with patch.dict(os.environ, env, clear=True):
        # Re-import the settings module to pick up the cleared env
        import importlib

        import src.config.settings as settings_mod

        importlib.reload(settings_mod)
        assert settings_mod.EXPORT_DIR == "./exports"


def test_export_base_url_default_when_env_unset():
    """EXPORT_BASE_URL defaults to '/exports' when the env var is not set."""
    env = {k: v for k, v in os.environ.items() if k != "EXPORT_BASE_URL"}
    with patch.dict(os.environ, env, clear=True):
        import importlib

        import src.config.settings as settings_mod

        importlib.reload(settings_mod)
        assert settings_mod.EXPORT_BASE_URL == "/exports"


def test_export_dir_reads_from_env(tmp_path):
    """EXPORT_DIR uses the value from the EXPORT_DIR environment variable."""
    custom_dir = str(tmp_path / "custom_exports")
    with patch.dict(os.environ, {"EXPORT_DIR": custom_dir}):
        import importlib

        import src.config.settings as settings_mod

        importlib.reload(settings_mod)
        assert settings_mod.EXPORT_DIR == custom_dir


def test_export_base_url_reads_from_env():
    """EXPORT_BASE_URL uses the value from the EXPORT_BASE_URL environment variable."""
    with patch.dict(os.environ, {"EXPORT_BASE_URL": "/custom/exports"}):
        import importlib

        import src.config.settings as settings_mod

        importlib.reload(settings_mod)
        assert settings_mod.EXPORT_BASE_URL == "/custom/exports"
