import json
import logging
from pathlib import Path
import pandas as pd
import argparse

# Set up basic logging configuration
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def convert_json(
    json_filepath: str, parquet_filepath: str, cols_to_convert: list[str] = None
) -> None:
    """
    Cleans the yearly metrics data from a JSON file and saves it as a Parquet file.

    Parameters
    ----------
    json_filepath : str
        The path to the JSON file containing the data.
    parquet_filepath : str
        The path where the cleaned Parquet file should be saved.
    cols_to_convert : list of str, optional
        List of column names to convert to timedelta. If None, a default list is used.

    Returns
    -------
    None
    """
    if cols_to_convert is None:
        cols_to_convert = [
            "time_to_first_response",
            "time_to_close",
            "time_to_answer",
            "time_in_draft",
        ]

    try:
        json_path = Path(json_filepath)
        if not json_path.exists():
            logging.error(f"JSON file not found: {json_filepath}")
            return

        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if "issues" not in data:
            logging.error("Key 'issues' not found in JSON data.")
            return

        df = pd.DataFrame(data["issues"])

        # Convert specified columns to timedelta if they exist, log a warning if not found
        for col in cols_to_convert:
            if col in df.columns:
                df[col] = pd.to_timedelta(df[col], errors="coerce")
            else:
                logging.warning(
                    f"Column '{col}' not found in data; skipping conversion."
                )

        # Log availability of enriched columns
        for col in ["milestone", "user", "assignees"]:
            if col not in df.columns:
                logging.warning(f"Optional column '{col}' not found in data.")

        # Convert "created_at" to datetime and set as index if present
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
            df["created_at"] = df["created_at"].dt.tz_localize(None)
            df.set_index("created_at", inplace=True)
        else:
            logging.error("Column 'created_at' not found in data. Cannot set index.")
            return

        # Drop the "label_metrics" column if it exists
        if "label_metrics" in df.columns:
            df.drop(columns="label_metrics", inplace=True)

        # Write the cleaned DataFrame to a Parquet file
        parquet_path = Path(parquet_filepath)
        df.to_parquet(parquet_path)
        logging.info(f"Parquet file saved successfully to {parquet_filepath}.")

    except Exception as e:
        logging.exception(f"An error occurred during conversion: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert issue metrics JSON to Parquet."
    )
    parser.add_argument("json_file", type=str, help="Path to the input JSON file")
    parser.add_argument(
        "parquet_file", type=str, help="Path to the output Parquet file"
    )
    args = parser.parse_args()

    convert_json(args.json_file, args.parquet_file)
