#TESTA analysis.py

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from unittest.mock import patch
client = TestClient(app)

@patch("app.api.analysis.perform_initial_scan")
def test_analyze_endpoint_flow(mock_scan):
    """Verifica che /analyze chiami il servizio e ritorni JSON con report_path"""
    mock_scan.return_value = {
        "repository": "test/repo",
        "main_license": "MIT",
        "compatibility_score": 90,
        "issues": [],
        "report_path": "/tmp/report.json"
    }
    payload = {"owner": "test", "repo": "repo"}
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["repository"] == "test/repo"
    assert "report" in data["report_path"]

@patch("app.api.analysis.perform_download")
def test_download_endpoint(mock_download):
    """Testa il download dello zip"""
    # Creiamo un file temporaneo finto da servire
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"fake zip content")
        tmp_path = tmp.name

    mock_download.return_value = tmp_path

    response = client.post("/api/download", json={"owner": "a", "repo": "b"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    # Cleanup (opzionale, o gestito dal test runner)
    import os
    os.unlink(tmp_path)