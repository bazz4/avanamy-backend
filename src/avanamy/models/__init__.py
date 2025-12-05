from avanamy.db.database import Base
from .tenant import Tenant

# Import all models so Alembic can discover them
from .api_spec import ApiSpec
from .documentation_artifact import DocumentationArtifact
from .generation_job import GenerationJob
from .version_history import VersionHistory
