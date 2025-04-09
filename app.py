import hvplot.pandas  # noqa
import pandas as pd
import panel as pn

pn.extension("tabulator")


# Helper functions
def load_data(file_path):
    try:
        return pd.read_parquet(file_path)
    except Exception as e:
        raise RuntimeError("Failed to load data. Consider using a CSV format.") from e


def compute_metrics(df):
    metrics = {}
    metrics["first_month"] = df.index[-1].strftime("%B %Y")
    metrics["last_month"] = df.index[0].strftime("%B %Y")
    metrics["total_issues"] = len(df)
    metrics["still_open"] = len(df[df["time_to_close"].isna()])
    metrics["closed"] = len(df[df["time_to_close"].notna()])
    metrics["avg_close_time"] = int(df["time_to_close"].mean().days)
    metrics["median_close_time"] = int(df["time_to_close"].median().days)
    return metrics


def format_issue_url(url):
    try:
        return f'<a href="{url}" target="_blank">{url.split("/")[-1]}</a>'
    except Exception:
        return url


# Data loading
df = load_data("yearly_metrics.parq")
metrics = compute_metrics(df)


# Plots
def create_comparison_plot(df):
    monthly_opened = df.resample("ME").size()
    monthly_closed = df.dropna(subset=["time_to_close"]).resample("ME").size()
    comparison_df = pd.DataFrame({"Opened": monthly_opened, "Closed": monthly_closed})
    return comparison_df.hvplot.line(
        xlabel="Month",
        ylabel="Number of Issues",
        title="Opened vs Closed Issues per Month",
        group_label="Issues",
    )


def create_issues_plot(df):
    cumulative_open_issues = (
        df.dropna(subset=["time_to_close"]).resample("D").size().cumsum()
    )
    cumulative_open_issues.name = "Cumulative Open Issues"
    return cumulative_open_issues.hvplot.line(
        xlabel="Date",
        ylabel="Cumulative Issues",
        title="Cumulative Open Issues Over Time",
    )


def create_author_plot(df):
    author_counts = df.groupby("author").size().sort_values(ascending=False).head(10)
    author_counts.name = "Number of Issues"
    return author_counts.hvplot.bar(
        xlabel="Author",
        ylabel="Number of Issues",
        title="Authors with the most Issues",
        rot=45,
    )


comparison_plot = create_comparison_plot(df)
cumulative_open_issues_plot = create_issues_plot(df)
author_plot = create_author_plot(df)

# Dashboard

# Shorten 'html_url' column and convert to clickable links
df["issue_no"] = df["html_url"].apply(format_issue_url)

styles = {
    "box-shadow": "rgba(50, 50, 93, 0.25) 0px 6px 12px -2px, rgba(0, 0, 0, 0.3) 0px 3px 7px -3px",
    "border-radius": "5px",
    "padding": "10px",
}


indicators = pn.FlexBox(
    pn.indicators.Number(
        value=metrics["total_issues"],
        name="Total Issues",
        default_color="blue",
        styles=styles,
    ),
    pn.indicators.Number(
        value=metrics["still_open"],
        name="Issues opened",
        default_color="green",
        styles=styles,
    ),
    pn.indicators.Number(
        value=metrics["closed"],
        name="Issues closed",
        default_color="red",
        styles=styles,
    ),
    pn.indicators.Number(
        value=metrics["avg_close_time"],
        name="Avg. time to close (days)",
        default_color="gray",
        styles=styles,
    ),
    pn.indicators.Number(
        value=metrics["median_close_time"],
        name="Median time to close (days)",
        default_color="blue",
        styles=styles,
    ),
)

issue_filter = pn.widgets.TextInput(name="Filter by Issue Number", placeholder="6552")
status_filter = pn.widgets.Select(
    name="Filter by Issue Status", options=["All", "Open", "Closed"], value="All"
)


# Function to return the filtered DataFrame based on widget values:
def get_filtered_df():
    filtered = df.copy()
    if issue_filter.value:
        # Filter the 'issue_no' column (converted to string for partial matching)
        filtered = filtered[
            filtered["issue_no"].astype(str).str.contains(issue_filter.value)
        ]
    if status_filter.value != "All":
        if status_filter.value == "Open":
            # Use pd.isna() to identify open issues (i.e., missing time_to_close)
            filtered = filtered[filtered["time_to_close"].isna()]
        elif status_filter.value == "Closed":
            # Use notna() to identify closed issues (i.e., having a time_to_close value)
            filtered = filtered[filtered["time_to_close"].notna()]
    return filtered


# Columns to convert to str for proper display in the tabulator
timedelta_columns = [
    "time_to_first_response",
    "time_to_close",
]
for col in timedelta_columns:
    df[f"{col}_str"] = df[col].astype(str)

table = pn.widgets.Tabulator(
    df,
    sizing_mode="stretch_width",
    name="Table",
    hidden_columns=[
        "html_url",  # shown as issue_no in tabulator
        "time_to_answer",  # NaN col
        "time_in_draft",  # NaN col
        "time_to_first_response",  # shown in str format in tabulator
        "time_to_close",  # shown in str format in tabulator
    ],
    pagination="remote",
    page_size=5,
    formatters={"issue_no": "html"},
)


# Callback function to update the table based on filter changes:
def update_table(event):
    table.value = get_filtered_df()


# Watch for changes in the filter widgets and update the table:
issue_filter.param.watch(update_table, "value")
status_filter.param.watch(update_table, "value")

tabs = pn.Tabs(
    ("Open vs Closed Issues", comparison_plot),
    ("Issue Authors", author_plot),
    ("Open Issues over time", cumulative_open_issues_plot),
    sizing_mode="scale_both",
    margin=10,
)

logo = '<img src="https://holoviz.org/_static/holoviz-logo.svg">'


text = f""" # [Panel](https://panel.holoviz.org) dashboard with Issue metrics from {metrics["first_month"]} to {metrics["last_month"]}.
"""

template = pn.Column(
    text,
    "## Summary Insights",
    indicators,
    "## Data table",
    pn.Row(issue_filter, status_filter),
    table,
    "## Plots",
    tabs,
)

template.servable()
