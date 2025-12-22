import json
from unittest.mock import MagicMock

from avanamy.models.api_spec import ApiSpec
from avanamy.services.documentation_service import (
    ARTIFACT_TYPE_API_HTML,
    ARTIFACT_TYPE_API_MARKDOWN,
    generate_and_store_markdown_for_spec,
    regenerate_all_docs_for_spec,
)
from uuid import UUID
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
    from avanamy.models.version_history import VersionHistory

    tenant, provider, product = tenant_provider_product
    spec = _make_spec(db, tenant, provider, product)

    # Create a version history record for the spec
    version_history = VersionHistory(
        api_spec_id=spec.id,
        version=5,
    )
    db.add(version_history)
    db.commit()
    db.refresh(version_history)

    uploads = []

    def fake_upload(key, data, content_type=None):
        uploads.append((key, content_type))
        return key, f"s3://bucket/{key}"

    repo = MagicMock()
    repo.get_latest.return_value = None
    repo.create = MagicMock()

    monkeypatch.setattr(
        "avanamy.services.documentation_service.upload_bytes",
        fake_upload,
    )
    # Patch the repository factory used in the module so the service
    # receives our `repo` instance when it calls `DocumentationArtifactRepository()`.
    monkeypatch.setattr(
        "avanamy.services.documentation_service.DocumentationArtifactRepository",
        lambda: repo,
    )

    md_key = generate_and_store_markdown_for_spec(db, spec)

    expected_slug = slugify_filename(spec.name)

    # ---------------------------------------------------------
    # Assertions (order-independent)
    # ---------------------------------------------------------
    keys = [k for k, _ in uploads]
    content_types = {k: ct for k, ct in uploads}

    # Ensure we uploaded markdown + HTML and returned the markdown key.
    md_upload_key = next(k for k, ct in uploads if ct == "text/markdown")
    html_upload_key = next(k for k, ct in uploads if ct == "text/html")
    assert md_key == md_upload_key

    # Validate S3 path invariants without coupling to exact formatting.
    expected_parts = [
        tenant.slug,
        provider.slug,
        product.slug,
        "v5",
        str(spec.id),
        expected_slug,
    ]
    assert all(part in md_upload_key for part in expected_parts)
    assert all(part in html_upload_key for part in expected_parts)
    assert md_upload_key.endswith(f"{expected_slug}.md")
    assert html_upload_key.endswith(f"{expected_slug}.html")

    assert content_types[md_upload_key] == "text/markdown"
    assert content_types[html_upload_key] == "text/html"

    # ---------------------------------------------------------
    # Artifacts created
    # ---------------------------------------------------------
    created_types = {call.kwargs["artifact_type"] for call in repo.create.call_args_list}

    # Ensure the repository was asked to create the expected artifact types.
    # Use superset check to avoid ordering/duplication flakiness.
    assert created_types.issuperset({
        ARTIFACT_TYPE_API_MARKDOWN,
        ARTIFACT_TYPE_API_HTML,
    })

    # The service sets `spec.documentation_html_s3_path` to the URL returned
    # by the uploader (e.g. "s3://bucket/{html_key}"). Ensure the expected
    # HTML key appears in the stored URL rather than relying on strict
    # `endswith`, which can be sensitive to prefixes.
    assert html_upload_key in (spec.documentation_html_s3_path or "")


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
