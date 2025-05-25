import pandas as pd
import hvplot.pandas  # noqa
import panel as pn
# from pyodide_http import patch_all

# patch_all()
pn.extension("tabulator", autoreload=True)


# Data loading
repo_files = {
    "HoloViews": "https://raw.githubusercontent.com/Azaya89/holoviz-insights/refs/heads/main/data/holoviews_metrics.parq",
    "hvPlot": "https://raw.githubusercontent.com/Azaya89/holoviz-insights/refs/heads/main/data/hvplot_metrics.parq",
    "Panel": "https://raw.githubusercontent.com/Azaya89/holoviz-insights/refs/heads/main/data/panel_metrics.parq",
}

repo_dfs = {name: pd.read_parquet(url) for name, url in repo_files.items()}
repo_selector = pn.widgets.Select(
    name="Select Repository", options=list(repo_files.keys()), value="HoloViews"
)


# Helper functions
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


styles = {
    "box-shadow": "rgba(50, 50, 93, 0.25) 0px 6px 12px -2px, rgba(0, 0, 0, 0.3) 0px 3px 7px -3px",
    "border-radius": "5px",
    "padding": "10px",
}


@pn.depends(repo_selector)
def indicators_view(repo):
    df = repo_dfs[repo]
    metrics = compute_metrics(df)
    return pn.FlexBox(
        pn.indicators.Number(
            value=metrics["total_issues"],
            name="Total Issues Opened",
            default_color="blue",
            styles=styles,
        ),
        pn.indicators.Number(
            value=metrics["still_open"],
            name="Issues still open",
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


@pn.depends(repo_selector)
def plots_view(repo):
    df = repo_dfs[repo]
    return pn.Tabs(
        ("Open vs Closed Issues", create_comparison_plot(df)),
        ("Issue Authors", create_author_plot(df)),
        ("Open Issues over time", create_issues_plot(df)),
        sizing_mode="scale_both",
        margin=10,
    )


@pn.depends(repo_selector)
def table_view(repo):
    df = repo_dfs[repo].copy()
    df["issue_no"] = df["html_url"].apply(format_issue_url)
    for col in ["time_to_first_response", "time_to_close"]:
        df[f"{col}_str"] = df[col].astype(str)
    return pn.widgets.Tabulator(
        df,
        sizing_mode="stretch_width",
        name="Table",
        hidden_columns=[
            "html_url",
            "time_to_answer",
            "time_in_draft",
            "time_to_first_response",
            "time_to_close",
        ],
        pagination="remote",
        page_size=5,
        formatters={"issue_no": "html"},
    )


@pn.depends(repo_selector)
def header_text(repo):
    df = repo_dfs[repo]
    metrics = compute_metrics(df)
    text = f"""
    ## [Panel](https://panel.holoviz.org) dashboard with Issue metrics from {metrics['first_month']} to {metrics['last_month']}.
    """

    return text


template = pn.Column(
    "# Holoviz Dashboard",
    header_text,
    repo_selector,
    "## Summary Insights",
    indicators_view,
    "## Data Table",
    table_view,
    "## Plots",
    plots_view,
)

template.servable()
