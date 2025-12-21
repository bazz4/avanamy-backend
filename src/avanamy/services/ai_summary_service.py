# src/avanamy/services/ai_summary_service.py

"""
AI Summary Service

Generates human-readable summaries of API changes using Claude API.
"""

from __future__ import annotations
import logging
import os
from opentelemetry import trace
import anthropic

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def generate_diff_summary(diff: dict, version_from: int, version_to: int) -> str | None:
    """
    Generate a human-readable summary of API changes using Claude API.
    
    Args:
        diff: The diff object with breaking/changes
        version_from: Previous version number
        version_to: Current version number
        
    Returns:
        Human-readable summary string, or None if generation fails
    """
    with tracer.start_as_current_span("service.generate_diff_summary") as span:
        span.set_attribute("version.from", version_from)
        span.set_attribute("version.to", version_to)
        span.set_attribute("diff.breaking", diff.get("breaking", False))
        span.set_attribute("diff.changes_count", len(diff.get("changes", [])))
        
        # Skip if no changes
        if not diff or not diff.get("changes"):
            logger.info("No changes in diff, skipping summary generation")
            return None
        
        # Get API key from environment
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set, skipping AI summary generation")
            span.set_attribute("summary.skipped", "no_api_key")
            return None
        
        try:
            client = anthropic.Anthropic(api_key=api_key)
            
            # Build prompt
            prompt = _build_summary_prompt(diff, version_from, version_to)
            
            logger.info(
                "Generating AI summary for v%d -> v%d (%d changes)",
                version_from,
                version_to,
                len(diff.get("changes", [])),
            )
            
            # Call Claude API
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract text from response
            summary = message.content[0].text if message.content else None
            
            if summary:
                span.set_attribute("summary.generated", True)
                span.set_attribute("summary.length", len(summary))
                logger.info("Generated AI summary: %d characters", len(summary))
            else:
                span.set_attribute("summary.generated", False)
                logger.warning("Claude API returned empty response")
            
            return summary
            
        except Exception:
            logger.exception("Failed to generate AI summary")
            span.set_attribute("summary.error", True)
            return None


def _build_summary_prompt(diff: dict, version_from: int, version_to: int) -> str:
    """
    Build the prompt for Claude to generate a summary.
    
    Args:
        diff: The diff object
        version_from: Previous version number
        version_to: Current version number
        
    Returns:
        Prompt string
    """
    breaking = diff.get("breaking", False)
    changes = diff.get("changes", [])
    
    prompt = f"""You are analyzing changes between version {version_from} and version {version_to} of an OpenAPI specification.

Here are the detected changes:

"""
    
    # Add each change
    for change in changes:
        change_type = change.get("type", "unknown")
        path = change.get("path", "")
        method = change.get("method", "")
        field = change.get("field", "")
        
        if method and field:
            prompt += f"- {change_type}: {method} {path} → {field}\n"
        elif method:
            prompt += f"- {change_type}: {method} {path}\n"
        else:
            prompt += f"- {change_type}: {path}\n"
    
    prompt += f"""
Breaking changes detected: {"Yes" if breaking else "No"}

Generate a concise, actionable summary (2-4 sentences) for developers explaining:
1. What changed in this version
2. The impact on API consumers (especially if breaking)
3. What action consumers need to take (if any)

Keep it concise and focused on developer impact. Use clear, direct language.
"""
    
    return prompt
