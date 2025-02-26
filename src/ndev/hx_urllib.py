import re


def extract_basename_from_url(url: str) -> str:
    """
    Extracts a repository name from the URL.
    For example, 'https://github.com/user/repo.git' -> 'repo'
    """
    matcher = re.search(r".*/([^/]+?)(?:\.git)?$", url)
    if matcher:
        return matcher.group(1)
    else:
        raise ValueError(f"Invalid repository URL: {url}")
