import asyncio
from bs4 import BeautifulSoup
from typing import Any, Dict
from urllib.parse import urljoin


async def check_imprint_page(html: str, url: str, http_client: Any = None) -> Dict[str, Any]:
    """Check for imprint page. Optionally verify the link is reachable."""
    result = {"check": "Imprint Page", "status": "FAIL", "details": ""}
    try:
        soup = BeautifulSoup(html, "html.parser")
        keywords = ["imprint", "impressum", "legal-notice"]

        for link in soup.find_all("a", href=True):
            href = link.get("href", "").lower()
            text = link.get_text().lower().strip()
            for kw in keywords:
                if kw in href or kw in text:
                    full_url = urljoin(url, link.get("href"))
                    result["status"] = "PASS"
                    result["details"] = f"Found: {full_url}"

                    if http_client:
                        resp = await http_client.get(full_url)
                        if resp["status"] != 200:
                            result["status"] = "WARN"
                            result["details"] = f"Link found but status {resp['status']}: {full_url}"
                    return result

        result["details"] = "No imprint link found"
    except Exception as e:
        result["status"] = "ERROR"
        result["details"] = str(e)
    return result
