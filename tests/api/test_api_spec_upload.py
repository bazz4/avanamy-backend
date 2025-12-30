import uuid
from types import SimpleNamespace
from unittest.mock import patch


def test_upload_api_spec_route(client, tenant_provider_product):
    tenant, provider, product = tenant_provider_product
    fake_spec = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="my.yaml",
        version="v1",
        description=None,
        parsed_schema='{"paths":{}}',
        original_file_s3_path="s3://test/my.yaml",
    )

    with patch(
        "avanamy.api.routes.api_specs.store_api_spec_file",
        return_value=fake_spec,
    ) as mock_store:
        response = client.post(
            f"/api-specs/upload?api_product_id={product.id}&provider_id={provider.id}",
            files={"file": ("my.yaml", b"content", "application/yaml")},
            headers={"X-Tenant-ID": str(tenant.id)},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(fake_spec.id)
    assert data["name"] == "my.yaml"
    assert data["original_file_s3_path"] == "s3://test/my.yaml"
    assert data["parsed_schema"] == {"paths": {}}

    mock_store.assert_called_once()
    kwargs = mock_store.call_args.kwargs
    assert kwargs["tenant_id"] == str(tenant.id)
    assert kwargs["api_product_id"] == product.id
    assert kwargs["provider_id"] == provider.id


def test_upload_api_spec_route_handles_failure(client, tenant_provider_product):
    tenant, provider, product = tenant_provider_product

    with patch(
        "avanamy.api.routes.api_specs.store_api_spec_file",
        return_value=None,
    ):
        response = client.post(
            f"/api-specs/upload?api_product_id={product.id}&provider_id={provider.id}",
            files={"file": ("bad.json", b"{}", "application/json")},
            headers={"X-Tenant-ID": str(tenant.id)},
        )

    assert response.status_code == 400
    assert "Failed to create API spec" in response.json()["detail"]


def test_upload_new_version_endpoint(client, tenant_provider_product):
    tenant, provider, product = tenant_provider_product
    existing_spec = SimpleNamespace(
        id=uuid.uuid4(),
        api_product_id=product.id,
        tenant_id=tenant.id,
        version="v1",
        description="old",
    )

    updated_spec = SimpleNamespace(
        id=existing_spec.id,
        api_product_id=product.id,
        tenant_id=tenant.id,
        version="v2",
        description="new",
        parsed_schema='{"paths":{}}',
        original_file_s3_path="s3://test/spec.json",
        name="spec.json",
    )

    with patch(
        "avanamy.api.routes.api_specs.ApiSpecRepository.get_by_id",
        return_value=existing_spec,
    ) as mock_repo, patch(
        "avanamy.api.routes.api_specs.update_api_spec_file",
        return_value=updated_spec,
    ) as mock_update:
        resp = client.post(
            f"/api-specs/{existing_spec.id}/upload-new-version",
            files={"file": ("spec.json", b"{}", "application/json")},
            headers={"X-Tenant-ID": str(tenant.id)},
        )

    assert resp.status_code == 200
    assert resp.json()["version"] == "v2"
    mock_repo.assert_called_once()
    mock_update.assert_called_once()


def test_upload_new_version_not_found(client):
    missing_id = uuid.uuid4()
    with patch(
        "avanamy.api.routes.api_specs.ApiSpecRepository.get_by_id",
        return_value=None,
    ):
        resp = client.post(
            f"/api-specs/{missing_id}/upload-new-version",
            files={"file": ("spec.json", b"{}", "application/json")},
            headers={"X-Tenant-ID": "tenant_other"},
        )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "API spec not found"
