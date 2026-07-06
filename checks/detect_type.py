import re


def detect_service_type(url: str, html: str = "", status_code: int = 0) -> str:
    """Detect if a service is frontend, backend/API, or unknown."""
    # API indicators in URL
    api_patterns = ['/api', '/rest', '/graphql', '/swagger', '/openapi', '/v1/', '/v2/']
    url_lower = url.lower()
    for p in api_patterns:
        if p in url_lower:
            return 'Backend'
    
    # If not reachable, we cannot determine the type reliably
    if status_code == 0 or status_code >= 400:
        return 'N/A'
    
    # If HTML response contains typical frontend elements
    if html:
        if re.search(r'<html|<body|<div|<head', html, re.IGNORECASE):
            return 'Frontend'
        # JSON responses indicate API
        if html.strip().startswith('{') or html.strip().startswith('['):
            return 'Backend'
    
    return 'Unknown'
