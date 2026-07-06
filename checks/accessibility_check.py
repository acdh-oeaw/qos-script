from bs4 import BeautifulSoup


def check_accessibility(html: str, url: str = "") -> dict:
    """Basic accessibility checks on the service page HTML."""
    result = {"check": "Accessibility", "status": "PASS", "details": "", "issues": []}
    try:
        soup = BeautifulSoup(html, "html.parser")
        issues = []

        html_tag = soup.find("html")
        if not html_tag or not html_tag.get("lang"):
            issues.append("Missing 'lang' attribute on <html> tag")

        images = soup.find_all("img")
        imgs_without_alt = [img.get("src", "unknown") for img in images if not img.get("alt")]
        if imgs_without_alt:
            issues.append(f"{len(imgs_without_alt)} image(s) missing 'alt' attribute")

        if not soup.find("title") or not soup.find("title").get_text().strip():
            issues.append("Missing or empty <title> tag")

        h1_tags = soup.find_all("h1")
        if not h1_tags:
            issues.append("No <h1> tag found")

        viewport = soup.find("meta", attrs={"name": "viewport"})
        if not viewport:
            issues.append("Missing viewport meta tag")

        inputs = soup.find_all("input")
        for inp in inputs:
            inp_type = inp.get("type", "text")
            if inp_type in ("hidden", "submit", "button"):
                continue
            inp_id = inp.get("id")
            if not inp_id or not soup.find("label", attrs={"for": inp_id}):
                if not inp.get("aria-label") and not inp.get("aria-labelledby"):
                    issues.append(f"Input '{inp_id or inp.get('name', 'unknown')}' missing associated label")

        if issues:
            result["status"] = "WARN" if len(issues) <= 2 else "FAIL"
            result["issues"] = issues
            result["details"] = "; ".join(issues)
        else:
            result["details"] = "Basic checks passed"

    except Exception as e:
        result["status"] = "ERROR"
        result["details"] = str(e)
    return result
