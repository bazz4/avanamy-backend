import logging
from opentelemetry import trace
from prometheus_client import Counter
from markdown import Markdown
from jinja2 import Template

from pathlib import Path

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Metric: count how many times HTML is rendered
html_render_counter = Counter(
    "avanamy_markdown_html_render_total",
    "Number of times Markdown was converted to HTML"
)

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "docs_base.html"


def render_markdown_to_html(markdown_text: str, title: str = "API Documentation") -> str:
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

        final_html = template.render(
            title=title,
            toc=toc_html,
            content=html_content,
        )

        logger.info("Successfully rendered HTML documentation")
        return final_html
