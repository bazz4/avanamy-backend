
from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.models.api_spec import ApiSpec




def test_create_api_spec(db):
    spec = ApiSpecRepository.create(
        db,
        name="Test API",
        version="1.0",
        description="demo",
        original_file_s3_path="s3://test.json",
        parsed_schema={"info": "test"},
    )
    assert spec.id is not None
    assert spec.name == "Test API"


def test_get_api_spec_by_id(db):
    created = ApiSpecRepository.create(
        db,
        name="Another API",
        original_file_s3_path="s3://file.json",
    )
    fetched = ApiSpecRepository.get_by_id(db, created.id)
    assert fetched.id == created.id


def test_list_all_specs(db):
    ApiSpecRepository.create(db, name="A", original_file_s3_path="s3://a")
    ApiSpecRepository.create(db, name="B", original_file_s3_path="s3://b")

    results = ApiSpecRepository.list_all(db)
    assert len(results) == 2


def test_delete_api_spec(db):
    spec = ApiSpecRepository.create(db, name="Delete Me", original_file_s3_path="x")
    deleted = ApiSpecRepository.delete(db, spec.id)
    assert deleted is True

    assert ApiSpecRepository.get_by_id(db, spec.id) is None
