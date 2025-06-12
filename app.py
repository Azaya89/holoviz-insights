import pandas as pd
import hvplot.pandas  # noqa
import panel as pn
import holoviews as hv
from holoviews import opts
# from pyodide_http import patch_all

# patch_all()
pn.extension("tabulator", autoreload=True)

status_filter = pn.widgets.RadioButtonGroup(
    name="Issue Status",
    options=["Open Issues", "Closed Issues", "All Issues"],
    value="All Issues",
    button_type="success",
)


# Data loading
data_url = (
    "https://raw.githubusercontent.com/Azaya89/holoviz-insights/refs/heads/main/data/"
)

repo_files = {
    "HoloViews": data_url + "holoviews_metrics.parq",
    "hvPlot": data_url + "hvplot_metrics.parq",
    "Panel": data_url + "panel_metrics.parq",
}

repo_dfs = {name: pd.read_parquet(url) for name, url in repo_files.items()}
repo_selector = pn.widgets.Select(
    name="Select Repository", options=list(repo_files.keys()), value="HoloViews"
)

release_files = {
    "HoloViews": data_url + "holoviews_releases.csv",
    "hvPlot": data_url + "hvplot_releases.csv",
    "Panel": data_url + "panel_releases.csv",
}

release_dfs = {
    name: pd.read_csv(url, parse_dates=["published_at"])
    for name, url in release_files.items()
}


def create_release_plot(df, repo_name):
    df = df.copy()
    type_order = ["patch", "minor", "major"]
    y_map = {k: v for v, k in enumerate(type_order, 1)}  # patch=1, minor=2, major=3
    df["type"] = pd.Categorical(df["type"], categories=type_order, ordered=True)
    df["y"] = df["type"].map(y_map).astype(float)
    # Sort by published_at descending (latest first)
    df = df.sort_values("published_at", ascending=False).reset_index(drop=True)
    # Compute rectangle bounds: each bar spans from this release to the next
    df["x0"] = df["published_at"]
    df["x1"] = df["published_at"].shift(
        1, fill_value=pd.Timestamp.now(tz=df["published_at"].dt.tz)
    )
    df["y0"] = df["y"] - 0.3
    df["y1"] = df["y"] + 0.3
    last_release = df.iloc[0]
    now = pd.Timestamp.now(tz=last_release["published_at"].tz)
    days_since = (now - last_release["published_at"]).days
    message = f"🔔 Last release was {days_since} days ago on {last_release['published_at'].date()} ({last_release['tag']})"

    rects = hv.Rectangles(
        df[["x0", "y0", "x1", "y1", "tag", "type", "published_at"]],
        kdims=["x0", "y0", "x1", "y1"],
        vdims=["tag", "type", "published_at"],
    )
    rects = rects.opts(
        opts.Rectangles(
            color="type",
            cmap={"major": "#eb2f40", "minor": "#0e9c24", "patch": "#0e67bb"},
            line_color="white",
            alpha=0.8,
            width=800,
            height=220,
            tools=["vline"],
            xlabel="Date",
            ylabel="",
            yticks=[(1, "patch"), (2, "minor"), (3, "major")],
            xrotation=30,
            show_legend=True,
            title=f"{repo_name} Release Timeline",
        )
    )
    return pn.Column(
        pn.pane.Markdown(
            f"**{message}**", styles={"color": "gray", "margin-bottom": "16px"}
        ),
        rects,
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
    # Calculate the number of open issues for each day (date only)
    df = df.copy()
    df["opened_date"] = df.index.normalize()
    df["closed_date"] = df["opened_date"] + df["time_to_close"]
    all_dates = pd.date_range(
        df["opened_date"].min(), pd.Timestamp.now().normalize(), freq="D"
    )
    open_counts = pd.Series(0, index=all_dates)
    for _, row in df.iterrows():
        start = row["opened_date"]
        end = row["closed_date"] if pd.notnull(row["closed_date"]) else all_dates[-1]
        # Use only the date part for the range
        open_range = pd.date_range(start, end, freq="D")
        open_counts.loc[open_range] += 1
    open_counts.name = "Open Issues"
    return open_counts.hvplot.line(
        xlabel="Date",
        ylabel="Number of Open Issues",
        title="Open Issues Over Time",
    )


def create_milestone_plot(df):
    # Filter to only include open issues (where time_to_close is null)
    df = df[df["time_to_close"].isna()]
    milestone_counts = df["milestone"].value_counts(dropna=False)
    return milestone_counts.hvplot.bar(
        title="Open Issues by Milestone",
        xlabel="Milestone",
        ylabel="Issue Count",
        rot=45,
        height=300,
        width=600,
    )


def create_milestone_summary(df):
    has_milestone = df["milestone"].notna().sum()
    no_milestone = df["milestone"].isna().sum()
    summary = pd.Series(
        [has_milestone, no_milestone], index=["Has Milestone", "No Milestone"]
    )
    return summary.hvplot.bar(
        title="Milestone Coverage",
        ylabel="Issue Count",
        xlabel="Milestone Presence",
        height=300,
        width=400,
    )


def create_releases_per_year_plot(release_df):
    release_df = release_df.copy()
    release_df["year"] = release_df["published_at"].dt.year
    releases_per_year = release_df.groupby("year").size()
    return releases_per_year.hvplot.bar(
        xlabel="Year",
        ylabel="Number of Releases",
        title="Releases per Year",
        hover_tooltips=[("Year", "@year"), ("Count", "@0")],
        height=300,
        width=600,
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


# State variable to store the active tab index
active_tab_index = [0]


@pn.depends(repo_selector)
def plots_view(repo):
    df = repo_dfs[repo]
    release_df = release_dfs[repo]
    tabs = pn.Tabs(
        ("Open vs Closed Issues", create_comparison_plot(df)),
        ("Open Issues over time", create_issues_plot(df)),
        ("Issues by Milestone", create_milestone_plot(df)),
        ("Milestone Coverage", create_milestone_summary(df)),
        ("Release History", create_release_plot(release_df, repo)),
        ("Releases per Year", create_releases_per_year_plot(release_df)),
        sizing_mode="scale_both",
        margin=10,
        dynamic=True,
        active=active_tab_index[0],
    )

    def on_tab_change(event):
        active_tab_index[0] = event.new

    tabs.param.watch(on_tab_change, "active")
    return tabs


@pn.depends(repo_selector, status_filter)
def table_view(repo, status):
    df = repo_dfs[repo].copy()
    if status == "Open Issues":
        df = df[df["time_to_close"].isna()]
    elif status == "Closed Issues":
        df = df[df["time_to_close"].notna()]
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
    ## {repo} dashboard with Issue metrics from {metrics["first_month"]} to {metrics["last_month"]}.
    """

    return text


template = pn.Column(
    "# Holoviz Dashboard",
    header_text,
    repo_selector,
    "## Summary Insights",
    indicators_view,
    "## Filter by Issue  Status",
    status_filter,
    "## Data Table",
    table_view,
    "## Plots",
    plots_view,
)

template.servable()
