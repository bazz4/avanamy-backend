
import json
from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.models.api_spec import ApiSpec
from avanamy.db.database import SessionLocal
        
def test_create_api_spec(db):
   
    parsed = {"info": "test"}
    parsed_json = json.dumps(parsed)

    spec = ApiSpecRepository.create(
        db,
        name="Test API",
        version="1.0",
        description="demo",
        original_file_s3_path="s3://test.json",
        parsed_schema=parsed_json,
    )
    assert spec.id is not None
    assert spec.name == "Test API"


def test_get_api_spec_by_id(db):

    parsed_json = json.dumps({"a": 1})

    created = ApiSpecRepository.create(
        db,
        name="Another API",
        version="1.0",
        description="demo",
        original_file_s3_path="s3://file.json",
        parsed_schema=parsed_json,
    )
    fetched = ApiSpecRepository.get_by_id(db, created.id)
    assert fetched.id == created.id


def test_list_all_specs(db):
   
    ApiSpecRepository.create(
        db,
        name="A",
        version=None,
        description=None,
        original_file_s3_path="s3://a",
        parsed_schema=None,
    )
    ApiSpecRepository.create(
        db,
        name="B",
        version=None,
        description=None,
        original_file_s3_path="s3://b",
        parsed_schema=None,
    )

    specs = ApiSpecRepository.list_all(db)
    assert len(specs) == 2


def test_delete_api_spec(db):
    spec = ApiSpecRepository.create(
        db, 
        name="Delete Me", 
        version="1.0",
        description="demo",
        original_file_s3_path="x",
        parsed_schema=None,)
    deleted = ApiSpecRepository.delete(db, spec.id)
    assert deleted is True

    assert ApiSpecRepository.get_by_id(db, spec.id) is None
