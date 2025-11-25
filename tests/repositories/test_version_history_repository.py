from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.repositories.version_history_repository import VersionHistoryRepository


def test_create_version_history(db):
    spec = ApiSpecRepository.create(db, name="Spec", original_file_s3_path="s3://x")

    vh = VersionHistoryRepository.create(
        db,
        api_spec_id=spec.id,
        version_label="v1",
        changelog="initial",
    )

    assert vh.id is not None
    assert vh.version_label == "v1"


def test_list_version_history_for_spec(db):
    spec = ApiSpecRepository.create(db, name="Spec", original_file_s3_path="s3://x")

    VersionHistoryRepository.create(db, api_spec_id=spec.id, version_label="v1")
    VersionHistoryRepository.create(db, api_spec_id=spec.id, version_label="v2")

    versions = VersionHistoryRepository.list_for_spec(db, spec.id)
    assert len(versions) == 2
