from prometheus_client import Counter

spec_upload_total = Counter(
    "avanamy_spec_upload_total",
    "Number of API specifications uploaded"
)

spec_parse_failures_total = Counter(
    "avanamy_spec_parse_failures_total",
    "Number of failed API spec parsing attempts"
)

markdown_generation_total = Counter(
    "avanamy_markdown_generation_total",
    "Number of times markdown documentation was generated"
)
