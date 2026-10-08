from bs4 import BeautifulSoup


def make_page_data(html: str, **overrides) -> dict:
    """Build the page_data dict analyzers expect, without fetching a URL."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    data = {
        "url": "https://example.com/running-shoes",
        "final_url": "https://example.com/running-shoes",
        "status_code": 200,
        "response_time_ms": 180.0,
        "redirect_count": 0,
        "headers": {
            "content-type": "text/html; charset=utf-8",
            "strict-transport-security": "max-age=31536000; includeSubDomains",
        },
        "html": html,
        "soup": soup,
        "page_title": title,
        "is_https": True,
    }
    data.update(overrides)
    return data


def checks_by_id(result) -> dict:
    return {check.id: check for check in result.checks}
