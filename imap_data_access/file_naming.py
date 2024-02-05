"""Methods for managing and validating filenames."""
import re

def extract_filename_components(filename: str):
    """
    Extracts all components from filename.

    Parameters
    ----------
    filename : str
        Path of dependency data.

    Returns
    -------
    components : dict
        Dictionary containing components.

    """
    pattern = (
        r"^imap_"
        r"(?P<instrument>[^_]+)_"
        r"(?P<datalevel>[^_]+)_"
        r"(?P<descriptor>[^_]*)_?"  # optional
        r"(?P<startdate>\d{8})_"
        r"(?P<enddate>\d{8})_"
        r"(?P<version>v\d{2}-\d{2})"
        r"\.(cdf|pkts)$"
    )
    match = re.match(pattern, filename)
    if match is None:
        return
    components = match.groupdict()
    return components
