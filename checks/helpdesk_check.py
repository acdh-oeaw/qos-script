from bs4 import BeautifulSoup

from checks.config import config


def check_helpdesk_email(html: str, expected_email: str = None) -> dict:
    """Check if the page HTML contains the helpdesk email address."""
    if expected_email is None:
        expected_email = config.get("helpdesk_email")

    result = {"check": "Helpdesk Email", "status": "FAIL", "details": ""}
    try:
        if expected_email in html:
            result["status"] = "PASS"
            result["details"] = f"Found {expected_email}"
            return result

        soup = BeautifulSoup(html, "html.parser")
        mailto_links = soup.find_all("a", href=lambda h: h and "mailto:" in h)
        for link in mailto_links:
            if expected_email in link.get("href", ""):
                result["status"] = "PASS"
                result["details"] = f"Found mailto link: {link.get('href')}"
                return result

        result["details"] = f"{expected_email} not found on the page"
    except Exception as e:
        result["status"] = "ERROR"
        result["details"] = str(e)
    return result
