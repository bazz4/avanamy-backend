import logging
from opentelemetry import trace
from prometheus_client import Counter
from markdown import Markdown
from jinja2 import Template
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Metric: count how many times HTML is rendered
html_render_counter = Counter(
    "avanamy_markdown_html_render_total",
    "Number of times Markdown was converted to HTML"
)

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "docs_base.html"


def render_markdown_to_html(
    markdown_text: str, 
    title: str = "API Documentation",
    provider_name: str = None,
    product_name: str = None,
    version_label: str = None,
    spec_version: str = None
) -> str:
    """
    Convert Markdown into styled HTML using our template.
    Includes:
      - TOC generation
      - Syntax highlighting
    """

    with tracer.start_as_current_span("render_markdown_to_html") as span:
        logger.debug("Rendering Markdown to HTML...")

        html_render_counter.inc()
        span.set_attribute("markdown.length", len(markdown_text))

        # Markdown with TOC and fenced code blocks
        md = Markdown(
            extensions=[
                "toc",
                "fenced_code",
                "codehilite",
                "tables",
                "admonition",
            ]
        )

        html_content = md.convert(markdown_text)

        toc_html = md.toc or "<p><em>No table of contents available</em></p>"

        # Load template
        template_str = TEMPLATE_PATH.read_text(encoding="utf-8")
        template = Template(template_str)
        
        from datetime import datetime
        
        final_html = template.render(
            provider_name=provider_name or "Provider",
            product_name=product_name or "Product",
            spec_title=title,  # "Test Diff Engineer" from the spec
            spec_version=spec_version or "1.0.0",  # From spec's info.version
            version_label=version_label or "v1",  # Our internal version (v9)
            toc=toc_html,
            content=html_content,
            now=datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC"),
        )

        logger.info("Successfully rendered HTML documentation")
        return final_html