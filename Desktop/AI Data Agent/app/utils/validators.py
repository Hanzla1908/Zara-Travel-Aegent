import os
import pandas as pd

MAX_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".csv":     "CSV (comma-separated values)",
    ".xlsx":    "Excel 2007+ workbook",
    ".xls":     "Excel 97-2003 workbook",
    ".parquet": "Apache Parquet",
    ".json":    "JSON",
}


def validate_upload(filename: str, size_bytes: int) -> None:
    """Raise ValueError with a clear message if the file cannot be accepted."""
    if not filename or "." not in filename:
        raise ValueError(
            f"File has no extension. Supported types: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"'{ext}' is not supported. "
            f"Accepted types: {', '.join(ALLOWED_EXTENSIONS.keys())}"
        )

    max_bytes = MAX_MB * 1024 * 1024
    if size_bytes > max_bytes:
        actual_mb = round(size_bytes / 1024 / 1024, 1)
        raise ValueError(
            f"File is {actual_mb} MB, which exceeds the {MAX_MB} MB limit. "
            "Try splitting it into smaller files, or increase MAX_UPLOAD_MB in .env."
        )

    if size_bytes == 0:
        raise ValueError("File appears to be empty (0 bytes).")


def validate_dataframe(df: pd.DataFrame) -> None:
    """Raise ValueError if the loaded DataFrame is unusable."""
    if df is None:
        raise ValueError("No data was returned by the file reader.")

    if len(df.columns) == 0:
        raise ValueError(
            "The file parsed to a table with no columns. "
            "Check that the file is not corrupted and has a header row."
        )

    if df.empty:
        raise ValueError(
            "The file contains column headers but no data rows. "
            "Ensure the file has at least one data row below the header."
        )
