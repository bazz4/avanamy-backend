# src/avanamy/tracing.py

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def configure_tracing(service_name: str = "avanamy-backend") -> None:
    """
    Configure OpenTelemetry tracing with a console exporter.

    Right now this just prints spans to stdout so we can see that tracing works.
    Later we can swap ConsoleSpanExporter for OTLP/Tempo without changing callers.
    """
    # If there's already a provider, don't reconfigure
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return

    provider = TracerProvider()
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)

    # Optional: you could set resource/service name here when we wire to Tempo
    # from opentelemetry.sdk.resources import Resource
    # provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
