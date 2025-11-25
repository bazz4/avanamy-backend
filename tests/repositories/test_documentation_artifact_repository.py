from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.repositories.documentation_artifact_repository import DocumentationArtifactRepository


def test_create_artifact(db):
    spec = ApiSpecRepository.create(db, name="Spec", original_file_s3_path="s3://x")

    artifact = DocumentationArtifactRepository.create(
        db,
        api_spec_id=spec.id,
        artifact_type="markdown",
        s3_path="s3://output.md",
    )

    assert artifact.id is not None
    assert artifact.artifact_type == "markdown"


def test_list_artifacts_for_spec(db):
    spec = ApiSpecRepository.create(db, name="Spec", original_file_s3_path="s3://x")

    DocumentationArtifactRepository.create(db, api_spec_id=spec.id, artifact_type="md", s3_path="a")
    DocumentationArtifactRepository.create(db, api_spec_id=spec.id, artifact_type="html", s3_path="b")

    artifacts = DocumentationArtifactRepository.list_for_spec(db, spec.id)
    assert len(artifacts) == 2
