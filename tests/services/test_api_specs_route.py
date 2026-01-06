from types import SimpleNamespace
import uuid
from unittest.mock import ANY, MagicMock, patch


def test_regenerate_docs_endpoint_success(client):
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    fake_spec = SimpleNamespace(id=spec_id, api_product_id=uuid.uuid4())

    with patch(
        "avanamy.api.routes.api_specs.ApiSpecRepository.get_by_id",
        return_value=fake_spec,
    ) as mock_repo, patch(
        "avanamy.api.routes.api_specs.regenerate_all_docs_for_spec",
        new=MagicMock(return_value=("docs/md.md", "docs/html.html")),
    ) as mock_regen:
        resp = client.post(
            f"/api-specs/{spec_id}/regenerate-docs",
            headers={"X-Tenant-ID": str(tenant_id)},
        )

    assert resp.status_code == 200
    assert resp.json()["markdown_s3_path"] == "docs/md.md"
    assert resp.json()["html_s3_path"] == "docs/html.html"
    mock_repo.assert_called_once_with(db=ANY, spec_id=spec_id, tenant_id=tenant_id)
    mock_regen.assert_called_once_with(ANY, fake_spec)


def test_regenerate_docs_endpoint_returns_400_on_generation_failure(client):
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    fake_spec = SimpleNamespace(id=spec_id, api_product_id=uuid.uuid4())

    with patch(
        "avanamy.api.routes.api_specs.ApiSpecRepository.get_by_id",
        return_value=fake_spec,
    ), patch(
        "avanamy.api.routes.api_specs.regenerate_all_docs_for_spec",
        new=MagicMock(return_value=(None, None)),
    ):
        resp = client.post(
            f"/api-specs/{spec_id}/regenerate-docs",
            headers={"X-Tenant-ID": str(tenant_id)},
        )

    assert resp.status_code == 400
    assert "Failed to regenerate documentation" in resp.json()["detail"]


def test_regenerate_docs_endpoint_not_found(client):
    spec_id = uuid.uuid4()
    tenant_id = "tenant_test123"
    with patch(
        "avanamy.api.routes.api_specs.ApiSpecRepository.get_by_id",
        return_value=None,
    ):
        resp = client.post(
            f"/api-specs/{spec_id}/regenerate-docs",
            headers={"X-Tenant-ID": tenant_id},
        )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "API spec not found"
