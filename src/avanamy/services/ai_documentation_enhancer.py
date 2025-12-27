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
        spec: Dict[str, Any]
    ) -> str:
        """
        Enhance basic markdown documentation with AI-generated content.
        
        Args:
            basic_markdown: The basic generated markdown
            spec: The normalized OpenAPI spec
            
        Returns:
            Enhanced markdown with AI additions
        """
        if not self.client:
            logger.warning("AI enhancement skipped - no API key")
            return basic_markdown
        
        with tracer.start_as_current_span("ai.enhance_markdown") as span:
            try:
                # Extract key info from spec
                api_name = spec.get("info", {}).get("title", "API")
                endpoints_count = len(spec.get("paths", {}))
                
                span.set_attribute("api.name", api_name)
                span.set_attribute("endpoints.count", endpoints_count)
                
                logger.info(f"Enhancing docs for {api_name} with {endpoints_count} endpoints")
                
                # Call Claude to enhance
                enhanced = await self._call_claude_for_enhancement(
                    basic_markdown,
                    spec
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
        spec: Dict[str, Any]
    ) -> str:
        """
        Call Claude API to enhance the documentation.
        
        Uses a carefully crafted prompt to add value without
        making docs too long or redundant.
        """
        
        # Build the enhancement prompt
        prompt = self._build_enhancement_prompt(basic_markdown, spec)
        
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
        spec: Dict[str, Any]
    ) -> str:
        """Build the prompt for Claude to enhance docs."""
        
        api_name = spec.get("info", {}).get("title", "API")
        
        return f"""You are a technical writer enhancing API documentation.

Given this basic API documentation, enhance it to be more helpful for developers.

API Name: {api_name}

Original Documentation:
{basic_markdown}

OpenAPI Spec (for context):
{json.dumps(spec, indent=2)[:3000]}  # First 3000 chars for context

Please enhance this documentation by:

1. **Keep the existing structure** - Don't remove any sections
2. **Add a "Getting Started" section** at the top with:
   - Quick example of making your first API call
   - How to authenticate (based on spec)
   - Common workflow example
3. **For each endpoint**, add a subsection AFTER the examples called "💡 Important Notes" that includes:
   - 1-2 critical warnings if applicable (idempotency, rate limits, etc.)
   - Common use case (one sentence)
   - ONLY if truly important - don't add fluff
4. **Add an "Error Handling" section** at the end with:
   - Brief explanation of status codes (200, 400, 401, 429, 500)
   - How to handle rate limits
   - Retry best practices

Rules:
- Be concise - add value, not length
- Use realistic examples with actual-looking data
- Don't repeat generic best practices on every endpoint
- If an endpoint is straightforward, don't add notes
- Keep it developer-friendly and practical
- Return ONLY the enhanced markdown, no preamble

Enhanced Documentation:"""
    
    def is_enabled(self) -> bool:
        """Check if AI enhancement is available."""
        return self.client is not None