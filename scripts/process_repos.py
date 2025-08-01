import os
import subprocess

REPOS = {
    "holoviews": "holoviz/holoviews",
    "hvplot": "holoviz/hvplot",
    "panel": "holoviz/panel",
    "datashader": "holoviz/datashader",
}

MAINTAINERS = {
    "holoviews": ["hoxbro", "philippjfr", "jlstevens"],
    "hvplot": ["maximlt", "philippjfr", "hoxbro", "ahuang11"],
    "panel": ["philippjfr", "ahaung11", "maximlt", "hoxbro"],
    "datashader": ["jbednar", "philippjfr", "hoxbro", "amaloney"],
}

token = os.environ["GH_TOKEN"]

for name, repo in REPOS.items():
    json_in = f"data/{name}_metrics.json"
    json_out = f"data/{name}_updated.json"
    parquet_out = f"data/{name}_metrics.parq"
    csv_out = f"data/{name}_releases.csv"

    maintainers = ",".join(MAINTAINERS[name])
    subprocess.run(
        [
            "python",
            "scripts/update_issues.py",
            json_in,
            repo,
            json_out,
            "--maintainers",
            maintainers,
        ],
        check=True,
    )
    subprocess.run(
        ["python", "scripts/convert_json.py", json_out, parquet_out], check=True
    )
    subprocess.run(["python", "scripts/get_releases.py", repo, csv_out], check=True)
