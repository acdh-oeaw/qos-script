from bs4 import BeautifulSoup

from config import config


def check_acdh_logo(html: str, url: str = "") -> dict:
    """Check for ACDH logo in already-fetched HTML."""
    result = {"check": "ACDH Logo", "status": "FAIL", "details": ""}
    try:
        soup = BeautifulSoup(html, "html.parser")
        logo_patterns = config.get("checks", {}).get("logo_patterns", [])

        for img in soup.find_all("img"):
            src = (img.get("src") or "").lower()
            alt = (img.get("alt") or "").lower()
            cls = " ".join(img.get("class") or []).lower()
            for pattern in logo_patterns:
                if pattern in src or pattern in alt or pattern in cls:
                    result["status"] = "PASS"
                    result["details"] = f"Found logo pattern '{pattern}' in image"
                    return result

        page_text = html.lower()
        for pattern in logo_patterns:
            if pattern in page_text:
                result["status"] = "PASS"
                result["details"] = f"Pattern '{pattern}' found in page source"
                return result

        result["details"] = "No ACDH logo found"
    except Exception as e:
        result["status"] = "ERROR"
        result["details"] = str(e)
    return result
