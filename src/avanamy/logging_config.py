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
    Ensures trace_id/span_id always exist to avoid KeyError,
    even when logs originate before middleware or from external libraries.
    """

    class SafeFormatter(logging.Formatter):
        def format(self, record):
            # Ensure both fields exist to avoid KeyError
            if not hasattr(record, "trace_id"):
                record.trace_id = "-"
            if not hasattr(record, "span_id"):
                record.span_id = "-"
            return super().format(record)

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    fmt = "%(asctime)s [%(levelname)s] %(name)s [trace=%(trace_id)s span=%(span_id)s] - %(message)s"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SafeFormatter(fmt))

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    # Attach handler + TraceIdFilter
    handler.addFilter(TraceIdFilter())
    root_logger.addHandler(handler)

    # Optional noise reduction
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)