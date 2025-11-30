import logging
import sys
import os
from opentelemetry import trace


class TraceIdFilter(logging.Filter):
    """Logging filter that injects current OpenTelemetry trace and span ids
    into log records as `trace_id` and `span_id` fields.

    If no span is active, both fields are set to `-`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx is not None and getattr(ctx, "trace_id", 0):
                # trace_id is an int; format as 32-char hex to match OTel
                record.trace_id = format(ctx.trace_id, "032x")
                record.span_id = format(ctx.span_id, "016x")
            else:
                record.trace_id = "-"
                record.span_id = "-"
        except Exception:
            record.trace_id = "-"
            record.span_id = "-"
        return True

def configure_logging():
    """
    Configure application-wide logging.
    Outputs to stdout in a structured, container-friendly format.
    """

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Include trace/span ids in the formatted output so logs can be correlated
    # with traces.
    fmt = "%(asctime)s [%(levelname)s] %(name)s [trace=%(trace_id)s span=%(span_id)s] - %(message)s"

    logging.basicConfig(
        level=log_level,
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Attach filter to root logger so all records gain trace/span ids
    logging.getLogger().addFilter(TraceIdFilter())

    # Optional: reduce overly noisy logs (e.g., boto3)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
