import json
import pandas as pd


def convert_json(json_filepath, parquet_filepath, cols_to_convert=None):
    """
    Cleans the yearly metrics data from a JSON file and saves it as a Parquet file.

    Parameters
    ----------
    json_filepath: str
        The path to the JSON file containing the data.
    parquet_filepath: str
        The path where the cleaned Parquet file should be saved.
    cols_to_convert: list, optional
        List of column names to convert to timedelta. If None, a default list is used.

    Returns
    -------
    pd.DataFrame
        The cleaned DataFrame.
    """
    if cols_to_convert is None:
        cols_to_convert = [
            "time_to_first_response",
            "time_to_close",
            "time_to_answer",
            "time_in_draft",
        ]

    with open(json_filepath, "r") as f:
        data = json.load(f)

    df = pd.DataFrame(data["issues"])

    for col in cols_to_convert:
        df[col] = pd.to_timedelta(df[col], errors="coerce")

    df["created_at"] = pd.to_datetime(df["created_at"]).dt.tz_convert(None)
    df.set_index("created_at", inplace=True)

    if "label_metrics" in df.columns:
        df.drop(columns="label_metrics", inplace=True)

    return df.to_parquet(parquet_filepath)


json_file = "yearly_metrics.json"
parquet_file = "yearly_metrics.parq"

convert_json(json_file, parquet_file)
