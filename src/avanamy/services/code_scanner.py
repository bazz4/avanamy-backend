# src/avanamy/services/code_scanner.py

"""
Code Scanner Interface and Implementations

Pluggable scanner architecture:
- RegexScanner (ships now - 85% accuracy)
- ASTScanner (future - 95% accuracy)
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class EndpointMatch:
    """
    A detected API endpoint usage in code.
    """
    endpoint_path: str      # e.g., "/v1/users"
    http_method: str | None # e.g., "GET", "POST", or None if unknown
    file_path: str          # relative to repo root
    line_number: int
    code_context: str       # the actual line of code
    confidence: float       # 0.0 to 1.0
    detection_method: str   # "regex", "ast", "manual"


class CodeScanner(ABC):
    """
    Abstract base class for code scanners.
    
    This allows us to swap implementations:
    - RegexScanner (simple, fast, ships now)
    - ASTScanner (complex, accurate, future)
    """
    
    @abstractmethod
    def scan_file(self, file_path: str, file_content: str) -> List[EndpointMatch]:
        """
        Scan a single file for API endpoint usage.
        
        Args:
            file_path: Path to file (relative to repo root)
            file_content: Content of the file
            
        Returns:
            List of detected endpoint matches
        """
        pass
    
    @abstractmethod
    def supports_language(self, file_extension: str) -> bool:
        """
        Check if this scanner supports a given file type.
        
        Args:
            file_extension: e.g., ".ts", ".py", ".js"
            
        Returns:
            True if supported
        """
        pass


class RegexScanner(CodeScanner):
    """
    Regex-based code scanner for API endpoints.
    
    Supports: JavaScript, TypeScript, Python, C#, Java, Go, Ruby, PHP, Rust
    Accuracy: ~85-90%
    Speed: Very fast
    
    Catches:
    ✅ fetch('/v1/users')
    ✅ axios.get("/v1/orders")
    ✅ requests.post('/v1/payments')
    ✅ HttpClient.GetAsync("/v1/users")
    ✅ Full URLs: 'https://api.stripe.com/v1/charges'
    
    Misses:
    ❌ Template interpolation: fetch(`/v1/${resource}`)
    ❌ Constructed URLs: base + '/v1/users'
    ❌ Config-based: fetch(config.API_URL)
    """
    
    # Language-specific regex patterns
    PATTERNS = {
        'javascript': [
            # === Custom API wrapper patterns - Handle both quotes and template literals ===
            # With TypeScript generics - match both single and double quotes
            (r'''apiGet\s*<[^>]+>\s*\(\s*['"]([^'"]+)['"]''', 'GET'),
            (r'''apiPost\s*<[^>]+>\s*\(\s*['"]([^'"]+)['"]''', 'POST'),
            (r'''apiPut\s*<[^>]+>\s*\(\s*['"]([^'"]+)['"]''', 'PUT'),
            (r'''apiPatch\s*<[^>]+>\s*\(\s*['"]([^'"]+)['"]''', 'PATCH'),
            (r'''apiDelete\s*<[^>]+>\s*\(\s*['"]([^'"]+)['"]''', 'DELETE'),

            # Without TypeScript generics - match both single and double quotes
            (r'''apiGet\s*\(\s*['"]([^'"]+)['"]''', 'GET'),
            (r'''apiPost\s*\(\s*['"]([^'"]+)['"]''', 'POST'),
            (r'''apiPut\s*\(\s*['"]([^'"]+)['"]''', 'PUT'),
            (r'''apiDelete\s*\(\s*['"]([^'"]+)['"]''', 'DELETE'),
            (r'''apiPatch\s*\(\s*['"]([^'"]+)['"]''', 'PATCH'),

            # Template literals (backticks) - matches paths with ${} interpolation
            (r'''apiGet\s*(?:<[^>]+>)?\s*\(\s*`([^`]+)`''', 'GET'),
            (r'''apiPost\s*(?:<[^>]+>)?\s*\(\s*`([^`]+)`''', 'POST'),
            (r'''apiPut\s*(?:<[^>]+>)?\s*\(\s*`([^`]+)`''', 'PUT'),
            (r'''apiDelete\s*(?:<[^>]+>)?\s*\(\s*`([^`]+)`''', 'DELETE'),
            (r'''apiPatch\s*(?:<[^>]+>)?\s*\(\s*`([^`]+)`''', 'PATCH'),
            
            # === Standard fetch patterns ===
            (r'''fetch\s*\(\s*['"]([^'"]+)['"]''', None),
            (r'''fetch\s*\(\s*`([^`]+)`''', None),
            
            # === Axios patterns ===
            (r'''axios\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
            (r'''axios\s*\(\s*\{\s*method:\s*['"](\ w+)['"],\s*url:\s*['"]([^'"]+)['"]''', 'method'),
            
            # === Other HTTP libraries ===
            (r'''request\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
            (r'''http\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
            (r'''got\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
            (r'''superagent\.(get|post|put|del|patch)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
        ],
        
        'python': [
            # requests library
            (r'''requests\.(get|post|put|delete|patch|head|options)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
            
            # httpx library
            (r'''httpx\.(get|post|put|delete|patch|head|options)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
            
            # aiohttp library
            (r'''aiohttp\.(get|post|put|delete|patch|head|options)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
            
            # urllib
            (r'''urllib\.request\.urlopen\s*\(\s*['"]([^'"]+)['"]''', None),
            
            # Generic API endpoint strings
            (r'''['"]/(v\d+|api)/[^\s'"]+['"]''', None),
            
            # Full URLs
            (r'''['"](https?://[^'"]+/(v\d+|api)/[^\s'"]+)['"]''', None),
        ],
        
        'csharp': [
            # HttpClient methods
            (r'''HttpClient\s*\.\s*(GetAsync|PostAsync|PutAsync|DeleteAsync|PatchAsync|GetStringAsync|PostAsJsonAsync)\s*\(\s*"([^"]+)"''', 'method'),
            
            # RestSharp
            (r'''RestRequest\s*\(\s*"([^"]+)"''', None),
            (r'''client\.(Get|Post|Put|Delete|Patch)\s*<[^>]+>\s*\(\s*new\s+RestRequest\s*\(\s*"([^"]+)"''', 'method'),
            
            # Generic HTTP client
            (r'''(GetAsync|PostAsync|PutAsync|DeleteAsync)\s*\(\s*"([^"]+)"''', 'method'),
            
            # Generic API strings
            (r'''"/(v\d+|api)/[^\s"]+"''', None),
            (r'''"(https?://[^"]+/(v\d+|api)/[^\s"]+)"''', None),
        ],
        
        'java': [
            # HttpClient (Java 11+)
            (r'''HttpRequest\s*\.\s*newBuilder\s*\(\s*URI\s*\.\s*create\s*\(\s*"([^"]+)"''', None),
            
            # OkHttp
            (r'''Request\s*\.\s*Builder\s*\(\s*\)\s*\.\s*url\s*\(\s*"([^"]+)"''', None),
            
            # Apache HttpClient
            (r'''HttpGet\s*\(\s*"([^"]+)"''', 'GET'),
            (r'''HttpPost\s*\(\s*"([^"]+)"''', 'POST'),
            (r'''HttpPut\s*\(\s*"([^"]+)"''', 'PUT'),
            (r'''HttpDelete\s*\(\s*"([^"]+)"''', 'DELETE'),
            
            # RestTemplate (Spring)
            (r'''restTemplate\.(get|post|put|delete|patch)ForObject\s*\(\s*"([^"]+)"''', 'method'),
            
            # Generic API strings
            (r'''"/(v\d+|api)/[^\s"]+"''', None),
            (r'''"(https?://[^"]+/(v\d+|api)/[^\s"]+)"''', None),
        ],
        
        'go': [
            # http.Get, http.Post, etc.
            (r'''http\.(Get|Post|Put|Delete|Head)\s*\(\s*"([^"]+)"''', 'method'),
            
            # http.NewRequest
            (r'''http\.NewRequest\s*\(\s*"(GET|POST|PUT|DELETE|PATCH)"\s*,\s*"([^"]+)"''', 'method'),
            
            # Client.Do patterns
            (r'''NewRequest\s*\(\s*"(GET|POST|PUT|DELETE|PATCH)"\s*,\s*"([^"]+)"''', 'method'),
            
            # Generic API strings
            (r'''"/(v\d+|api)/[^\s"]+"''', None),
            (r'''"(https?://[^"]+/(v\d+|api)/[^\s"]+)"''', None),
        ],
        
        'ruby': [
            # Net::HTTP
            (r'''Net::HTTP\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
            
            # HTTParty
            (r'''HTTParty\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
            
            # Faraday
            (r'''Faraday\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
            
            # RestClient
            (r'''RestClient\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]''', 'method'),
            
            # Generic API strings
            (r'''['"]/(v\d+|api)/[^\s'"]+['"]''', None),
            (r'''['"](https?://[^'"]+/(v\d+|api)/[^\s'"]+)['"]''', None),
        ],
        
        'php': [
            # Guzzle
            (r'''->get\s*\(\s*['"]([^'"]+)['"]''', 'GET'),
            (r'''->post\s*\(\s*['"]([^'"]+)['"]''', 'POST'),
            (r'''->put\s*\(\s*['"]([^'"]+)['"]''', 'PUT'),
            (r'''->delete\s*\(\s*['"]([^'"]+)['"]''', 'DELETE'),
            (r'''->patch\s*\(\s*['"]([^'"]+)['"]''', 'PATCH'),
            
            # cURL
            (r'''curl_setopt\s*\(\s*[^,]+,\s*CURLOPT_URL\s*,\s*['"]([^'"]+)['"]''', None),
            
            # file_get_contents
            (r'''file_get_contents\s*\(\s*['"]([^'"]+)['"]''', None),
            
            # Generic API strings
            (r'''['"]/(v\d+|api)/[^\s'"]+['"]''', None),
            (r'''['"](https?://[^'"]+/(v\d+|api)/[^\s'"]+)['"]''', None),
        ],
        
        'rust': [
            # reqwest
            (r'''reqwest::get\s*\(\s*"([^"]+)"''', 'GET'),
            (r'''client\.(get|post|put|delete|patch)\s*\(\s*"([^"]+)"''', 'method'),
            
            # hyper
            (r'''Request::get\s*\(\s*"([^"]+)"''', 'GET'),
            (r'''Request::post\s*\(\s*"([^"]+)"''', 'POST'),
            
            # Generic API strings
            (r'''"/(v\d+|api)/[^\s"]+"''', None),
            (r'''"(https?://[^"]+/(v\d+|api)/[^\s"]+)"''', None),
        ],
    }
    
    SUPPORTED_EXTENSIONS = {
        '.js', '.jsx', '.ts', '.tsx',  # JavaScript/TypeScript
        '.py',                          # Python
        '.cs',                          # C#
        '.java',                        # Java
        '.go',                          # Go
        '.rb',                          # Ruby
        '.php',                         # PHP
        '.rs',                          # Rust
    }
    
    LANGUAGE_MAP = {
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'javascript',
        '.tsx': 'javascript',
        '.py': 'python',
        '.cs': 'csharp',
        '.java': 'java',
        '.go': 'go',
        '.rb': 'ruby',
        '.php': 'php',
        '.rs': 'rust',
    }
    
    def supports_language(self, file_extension: str) -> bool:
        """Check if file extension is supported."""
        return file_extension.lower() in self.SUPPORTED_EXTENSIONS
    
    def scan_file(self, file_path: str, file_content: str) -> List[EndpointMatch]:
        """
        Scan a file for API endpoint usage using regex patterns.
        
        Args:
            file_path: Path to file (relative to repo root)
            file_content: Content of the file
            
        Returns:
            List of detected endpoint matches
        """
        # Determine language from extension
        file_ext = self._get_extension(file_path)
        if not self.supports_language(file_ext):
            return []
        
        language = self.LANGUAGE_MAP.get(file_ext)
        if not language:
            return []
        
        patterns = self.PATTERNS.get(language, [])
        matches = []
        
        # Scan line by line
        lines = file_content.split('\n')
        for line_num, line in enumerate(lines, start=1):
            # Skip comments
            if self._is_comment(line, language):
                continue
            
            # Try each pattern
            for pattern, method_group in patterns:
                for regex_match in re.finditer(pattern, line, re.IGNORECASE):
                    endpoint_match = self._extract_endpoint(
                        regex_match=regex_match,
                        method_group=method_group,
                        file_path=file_path,
                        line_number=line_num,
                        line_content=line,
                        language=language
                    )
                    
                    if endpoint_match:
                        matches.append(endpoint_match)
        
        logger.info(f"RegexScanner found {len(matches)} endpoints in {file_path}")
        return matches
    
    def _extract_endpoint(
        self, 
        regex_match: re.Match,
        method_group: str | None,
        file_path: str,
        line_number: int,
        line_content: str,
        language: str
    ) -> EndpointMatch | None:
        """
        Extract endpoint information from a regex match.
        
        Args:
            regex_match: The regex match object
            method_group: 'method' if HTTP method is in group 1, None otherwise
            file_path: Path to the file
            line_number: Line number where match was found
            line_content: The actual line of code
            language: Programming language
            
        Returns:
            EndpointMatch or None if invalid
        """
        try:
            groups = regex_match.groups()
            
            # Extract HTTP method and URL based on pattern structure
            if method_group == 'method':
                # Pattern like: axios.get('/v1/users')
                # Group 1 = method (get, post, etc.)
                # Group 2 = URL
                http_method = groups[0].upper() if groups[0] else None
                url = groups[1] if len(groups) > 1 else groups[0]
            elif isinstance(method_group, str) and method_group.isupper():
                # Fixed method like 'GET', 'POST'
                http_method = method_group
                url = groups[0]
            else:
                # Pattern like: fetch('/v1/users')
                # Group 1 = URL only
                http_method = None
                url = groups[0] if groups else regex_match.group(0)
            
            # Clean up the URL
            url = url.strip()
            
            # Skip if not a valid API endpoint pattern
            if not self._looks_like_api_endpoint(url):
                return None
            
            # Extract just the path from full URLs
            endpoint_path = self._extract_path_from_url(url)
            
            # Calculate confidence
            confidence = self._calculate_confidence(line_content, url, language)
            
            return EndpointMatch(
                endpoint_path=endpoint_path,
                http_method=http_method,
                file_path=file_path,
                line_number=line_number,
                code_context=line_content.strip(),
                confidence=confidence,
                detection_method="regex"
            )
            
        except Exception as e:
            logger.warning(f"Failed to extract endpoint from match: {e}")
            return None
    
    def _looks_like_api_endpoint(self, url: str) -> bool:
        """
        Check if a string looks like an API endpoint.

        Args:
            url: The URL string

        Returns:
            True if it looks like an API endpoint
        """
        # For custom API wrappers (apiGet, apiPost, etc.), trust that they're API calls
        # These are typically used only for API endpoints
        # For generic libraries (fetch, axios), we require /v or /api pattern

        # Must start with / (relative path) or be a full URL
        if not (url.startswith('/') or url.startswith('http://') or url.startswith('https://')):
            return False

        # Skip if it's just documentation or comments (but not API endpoints like /docs/)
        # Only filter out if these words appear in non-path contexts
        url_lower = url.lower()
        # Allow /docs/ as a path segment, but filter out URLs that are obviously not API endpoints
        if any(word in url_lower for word in ['example.com', 'placeholder', 'readme', 'documentation.html']):
            return False

        # Skip obvious non-API paths
        if url.startswith(('/static/', '/public/', '/assets/', '/images/')):
            return False

        return True
    
    def _extract_path_from_url(self, url: str) -> str:
        """
        Extract just the path from a full URL.
        
        Args:
            url: Full URL or path
            
        Returns:
            Just the path portion
            
        Examples:
            'https://api.stripe.com/v1/charges' -> '/v1/charges'
            '/v1/users' -> '/v1/users'
        """
        # If it's a full URL, extract path
        if url.startswith(('http://', 'https://')):
            match = re.search(r'https?://[^/]+(/.+)', url)
            if match:
                return match.group(1)
        
        # Already a path
        return url
    
    def _calculate_confidence(self, line: str, url: str, language: str) -> float:
        """
        Calculate confidence score for a match.
        
        Args:
            line: The line of code
            url: The detected URL
            language: Programming language
            
        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 1.0
        
        # Reduce confidence if URL contains template syntax
        # BUT: Simple variable substitution like ${id} is still pretty clear
        if '${' in url or '{' in url:
            # Count how many variables
            var_count = url.count('${')
            if var_count == 1:
                # Single variable like /users/${id} is still very clear
                confidence *= 0.85  # ← Changed from 0.6 to 0.85
            elif var_count == 2:
                # Two variables like /users/${id}/posts/${postId}
                confidence *= 0.75
            else:
                # Many variables - less confident
                confidence *= 0.6
        
        # Further reduce if there's complex logic in the template
        if '?' in url or ' ' in url:
            # Query params with variables or conditional logic
            confidence *= 0.8
        
        # Increase confidence if using known HTTP library
        http_libs = {
            'javascript': ['fetch', 'axios', 'request', 'http', 'got', 'apiGet', 'apiPost', 'apiPut', 'apiDelete', 'apiPatch'],
            'python': ['requests', 'httpx', 'aiohttp', 'urllib'],
            'csharp': ['HttpClient', 'RestSharp', 'GetAsync', 'PostAsync'],
            'java': ['HttpClient', 'OkHttp', 'RestTemplate', 'HttpGet', 'HttpPost'],
            'go': ['http.', 'NewRequest'],
            'ruby': ['HTTParty', 'Faraday', 'RestClient', 'Net::HTTP'],
            'php': ['Guzzle', 'curl_', 'file_get_contents'],
            'rust': ['reqwest', 'hyper'],
        }
        
        libs = http_libs.get(language, [])
        if any(lib in line for lib in libs):
            confidence = min(confidence * 1.1, 1.0)  # Slight boost, cap at 1.0
        
        # Reduce confidence if line looks like it might be commented
        if '//' in line[:line.find(url)] if url in line else False:
            confidence *= 0.5
        
        if '#' in line[:line.find(url)] if url in line else False:
            confidence *= 0.5
        
        return min(confidence, 1.0)
    
    def _is_comment(self, line: str, language: str) -> bool:
        """
        Check if a line is a comment.
        
        Args:
            line: Line of code
            language: Programming language
            
        Returns:
            True if line is a comment
        """
        stripped = line.strip()
        
        if language in ['javascript', 'csharp', 'java', 'go', 'rust', 'php']:
            # C-style comments
            if stripped.startswith('//'):
                return True
            if stripped.startswith('/*') or stripped.startswith('*'):
                return True
        
        if language == 'python':
            if stripped.startswith('#'):
                return True
            if stripped.startswith('"""') or stripped.startswith("'''"):
                return True
        
        if language == 'ruby':
            if stripped.startswith('#'):
                return True
            if stripped.startswith('=begin'):
                return True
        
        return False
    
    def _get_extension(self, file_path: str) -> str:
        """
        Get file extension from path.
        
        Args:
            file_path: Path to file
            
        Returns:
            File extension (e.g., '.py', '.js')
        """
        import os
        _, ext = os.path.splitext(file_path)
        return ext.lower()