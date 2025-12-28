"""
AI-powered documentation enhancement using Claude.

This service takes basic generated docs and enhances them with:
- Realistic examples
- Best practices warnings
- Error handling guidance
- Common use cases
"""

import logging
import os
from typing import Dict, Any, Optional
import json

from anthropic import Anthropic
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class AIDocumentationEnhancer:
    """
    Enhances API documentation using Claude AI.
    
    Adds contextual examples, best practices, and guidance
    that makes docs actually useful for developers.
    """
    
    def __init__(self):
        """Initialize Anthropic client from environment."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set - AI enhancement disabled")
            self.client = None
        else:
            self.client = Anthropic(api_key=api_key)
            logger.info("AI documentation enhancer initialized")
    
    async def enhance_markdown(
        self,
        basic_markdown: str,
        spec: Dict[str, Any],
        api_title: str = None
    ) -> str:
        """
        Enhance basic markdown documentation with AI-generated content.
        
        Args:
            basic_markdown: The basic generated markdown
            spec: The normalized OpenAPI spec
            api_title: Optional override for API title (defaults to spec's info.title)
            
        Returns:
            Enhanced markdown with AI additions
        """
        if not self.client:
            logger.warning("AI enhancement skipped - no API key")
            return basic_markdown
        
        with tracer.start_as_current_span("ai.enhance_markdown") as span:
            try:
                # Extract key info from spec
                if not api_title:
                    api_title = spec.get("info", {}).get("title", "API")
                
                endpoints_count = len(spec.get("paths", {}))
                
                span.set_attribute("api.name", api_title)
                span.set_attribute("endpoints.count", endpoints_count)
                
                logger.info(f"Enhancing docs for {api_title} with {endpoints_count} endpoints")
                
                # Call Claude to enhance
                enhanced = await self._call_claude_for_enhancement(
                    basic_markdown,
                    spec,
                    api_title  # Pass the title through
                )
                
                span.set_attribute("enhancement.success", True)
                return enhanced
                
            except Exception as e:
                logger.error(f"AI enhancement failed: {e}", exc_info=True)
                span.set_attribute("enhancement.success", False)
                # Return basic markdown if enhancement fails
                return basic_markdown
    
    async def _call_claude_for_enhancement(
        self,
        basic_markdown: str,
        spec: Dict[str, Any],
        api_title: str
    ) -> str:
        """
        Call Claude API to enhance the documentation.
        
        Uses a carefully crafted prompt to add value without
        making docs too long or redundant.
        """
        
        # Build the enhancement prompt
        prompt = self._build_enhancement_prompt(basic_markdown, spec, api_title)
        
        # Call Claude
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            temperature=0.3,  # Lower temperature for consistent, factual output
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        # Extract the enhanced markdown
        enhanced_markdown = message.content[0].text
        
        logger.info("Successfully enhanced documentation with AI")
        return enhanced_markdown
    
    def _build_enhancement_prompt(
        self,
        basic_markdown: str,
        spec: Dict[str, Any],
        api_title: str
    ) -> str:
        """Build the prompt for Claude to enhance docs."""
        
        return f"""You are a technical writer enhancing API documentation.

    Given this basic API documentation, enhance it to be more helpful for developers.

    API Name: {api_title}

    Original Documentation:
    {basic_markdown}

    OpenAPI Spec (for context):
    {json.dumps(spec, indent=2)[:3000]}  # First 3000 chars for context

    Please enhance this documentation by:

    1. **Start with an H1 title** using "{api_title}" exactly as written
    2. **Add a "Getting Started" section** at the H2 level with:
    - Brief welcome message explaining what this API does
    - Quick example of making your first API call
    - How to authenticate (based on spec's security schemes)
    - Common workflow example (2-3 steps)
    3. **For each endpoint**, add a subsection AFTER the examples called "💡 Important Notes" that includes:
    - 1-2 critical warnings if applicable (idempotency, rate limits, validation rules, etc.)
    - Common use case (one sentence)
    - ONLY add notes if truly important - skip if endpoint is straightforward
    4. **Add an "Error Handling" section** at the H2 level at the end with:
    - Brief explanation of HTTP status codes (200, 400, 401, 429, 500)
    - How to handle rate limits (if applicable)
    - Retry best practices
    5. **Improve section names**: If you see a section named "General", rename it to something more descriptive based on the endpoints it contains (e.g., "User Management", "Core Endpoints", "API Operations")

    Rules:
    - Be concise - add value, not length
    - Use realistic examples with actual-looking data (emails, phone numbers, IDs, dates)
    - Don't repeat generic best practices on every endpoint
    - Keep it developer-friendly and practical
    - Return ONLY the enhanced markdown, no preamble or explanation

    Enhanced Documentation:"""
    
    def is_enabled(self) -> bool:
        """Check if AI enhancement is available."""
        return self.client is not None