from avanamy.db.database import Base
from .tenant import Tenant

# Import all models so Alembic can discover them
from .provider import Provider
from .api_spec import ApiSpec
from .documentation_artifact import DocumentationArtifact
from .generation_job import GenerationJob
from .version_history import VersionHistory
from .api_product import ApiProduct
from .tenant import Tenant
from .watched_api import WatchedAPI
from .alert_configuration import AlertConfiguration
from .alert_history import AlertHistory
from .endpoint_health import EndpointHealth