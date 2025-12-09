import json
from unittest.mock import MagicMock

from avanamy.models.api_spec import ApiSpec
from avanamy.services.documentation_service import (
    ARTIFACT_TYPE_API_HTML,
    ARTIFACT_TYPE_API_MARKDOWN,
    generate_and_store_markdown_for_spec,
    regenerate_all_docs_for_spec,
)
from avanamy.utils.filename_utils import slugify_filename
from avanamy.utils.s3_paths import build_docs_markdown_path, build_docs_html_path


def _make_spec(db, tenant, provider, product):
    spec = ApiSpec(
        tenant_id=tenant.id,
        api_product_id=product.id,
        provider_id=provider.id,
        name="Demo Spec",
        version="v1",
        description="demo",
        original_file_s3_path="s3://temp",
        parsed_schema=json.dumps({"info": {"title": "X"}, "paths": {}}),
    )
    db.add(spec)
    db.commit()
    db.refresh(spec)
    return spec


def test_generate_and_store_markdown_for_spec_builds_keys(db, tenant_provider_product, monkeypatch):
    tenant, provider, product = tenant_provider_product
    spec = _make_spec(db, tenant, provider, product)

    uploads = []

    def fake_upload(key, data, content_type=None):
        uploads.append((key, content_type))
        return key, f"s3://bucket/{key}"

    repo = MagicMock()
    repo.get_latest.return_value = None

    monkeypatch.setattr(
        "avanamy.services.documentation_service.upload_bytes",
        fake_upload,
    )
    monkeypatch.setattr(
        "avanamy.services.documentation_service.DocumentationArtifactRepository",
        lambda: repo,
    )
    monkeypatch.setattr(
        "avanamy.services.documentation_service.VersionHistoryRepository.current_version_label_for_spec",
        lambda db, api_spec_id: "v5",
    )

    md_key = generate_and_store_markdown_for_spec(db, spec)

    expected_slug = slugify_filename(spec.name)
    expected_md = build_docs_markdown_path(
        tenant.slug,
        provider.slug,
        product.slug,
        "v5",
        spec.id,
        expected_slug,
    )
    expected_html = build_docs_html_path(
        tenant.slug,
        provider.slug,
        product.slug,
        "v5",
        spec.id,
        expected_slug,
    )

    assert md_key == expected_md
    assert uploads[0][0] == expected_md
    assert uploads[0][1] == "text/markdown"
    assert uploads[1][0] == expected_html
    assert uploads[1][1] == "text/html"

    # Two artifacts created when none exist
    created_types = {call.kwargs["artifact_type"] for call in repo.create.call_args_list}
    assert created_types == {ARTIFACT_TYPE_API_MARKDOWN, ARTIFACT_TYPE_API_HTML}
    assert spec.documentation_html_s3_path.endswith(expected_html)


def test_generate_and_store_markdown_returns_none_if_schema_missing(db, tenant_provider_product):
    tenant, provider, product = tenant_provider_product
    spec = ApiSpec(
        tenant_id=tenant.id,
        api_product_id=product.id,
        provider_id=provider.id,
        name="No Schema",
        version="v1",
        parsed_schema=None,
        original_file_s3_path="s3://noop",
    )
    db.add(spec)
    db.commit()

    assert generate_and_store_markdown_for_spec(db, spec) is None


def test_regenerate_all_docs_for_spec_computes_paths(db, tenant_provider_product, monkeypatch):
    tenant, provider, product = tenant_provider_product
    spec = _make_spec(db, tenant, provider, product)

    expected_slug = slugify_filename(spec.name)
    md_key = build_docs_markdown_path(
        tenant.slug,
        provider.slug,
        product.slug,
        "v2",
        spec.id,
        expected_slug,
    )

    monkeypatch.setattr(
        "avanamy.services.documentation_service.generate_and_store_markdown_for_spec",
        lambda _db, _spec: md_key,
    )
    monkeypatch.setattr(
        "avanamy.services.documentation_service.VersionHistoryRepository.current_version_label_for_spec",
        lambda _db, _spec_id: "v2",
    )
    html_key = build_docs_html_path(
        tenant.slug,
        provider.slug,
        product.slug,
        "v2",
        spec.id,
        expected_slug,
    )

    out_md, out_html = regenerate_all_docs_for_spec(db, spec)
    assert out_md == md_key
    assert out_html == html_key
