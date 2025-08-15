import babel
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from babel.languages import get_official_languages
from babel.numbers import format_compact_currency

st.set_page_config(layout="wide")


def main():
    """Main function to run the income distribution analysis app."""
    # Load data
    countries = load_countries()

    # Sidebar selection
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:

        def format_country_name(country_code):
            try:
                ret = countries[countries["alpha2"] == country_code][
                    "titlename"
                ].values[0]
            except IndexError:
                ret = country_code
            return str(ret)

        country_code = st.selectbox(
            "Select a country",
            options=list(countries["alpha2"]),
            format_func=format_country_name,
            index=countries["alpha2"].tolist().index("IN"),
        )

    # Load country-specific data
    df, meta = load_country_data(country_code)

    with col1:
        variable = st.selectbox(
            "Select a variable",
            meta["variable"],
            index=meta["variable"].tolist().index("aptincj992")
            if "aptincj992" in meta["variable"].tolist()
            else 0,
            format_func=lambda v: format_variable(v, meta),
        )
        var_meta = meta[meta["variable"] == variable]

    with col2:
        year = st.selectbox(
            "Select a year",
            sorted(df["year"].unique(), reverse=True),
            index=1 if len(df["year"].unique()) > 1 else 0,
        )

    with col3:
        groups = get_income_groups()
        group_name = st.selectbox(
            "Select a group",
            list(groups.keys()),
            index=1 if len(groups.keys()) > 1 else 0,
        )

    # Filter data
    filtered_df = filter_data(df, variable, year, group_name)

    if not len(filtered_df):
        st.error("No data available")
        st.stop()

    # Process data
    filtered_df = filtered_df[["percentile", "value"]]
    filtered_df["percentile"] = filtered_df["percentile"].apply(
        parse_percentile, convert_dtype=True
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        st.dataframe(filtered_df.sort_values(by="value"), hide_index=True)

    filtered_df["percentile"] = filtered_df["percentile"].apply(lambda x: x[0])
    filtered_df = filtered_df.sort_values(by="percentile")

    # Get currency conversion
    currency = var_meta["unit"].values[0]
    conversion_rate = get_currency_conversion_rate(currency)
    st.write(f"1 USD = {conversion_rate} {currency}")

    # Prepare summary data
    summary_df = prepare_summary_data(
        filtered_df, var_meta, country_code, conversion_rate
    )

    # Display summary
    col1, col2 = st.columns([1, 2])
    with col1:
        st.dataframe(
            summary_df,
            hide_index=True,
            column_order=["percentile", "usd", "local", "afford"],
        )
    with col2:
        fig = create_summary_plot(summary_df, variable, year, meta)
        st.plotly_chart(fig)

    # Detailed view controls
    col1, col2 = st.columns(2)
    with col1:
        start = st.number_input(
            "Start",
            min_value=0.0,
            max_value=100.0,
            step=0.001,
            value=0.0,
            format="%.3f",
        )
    with col2:
        end = st.number_input(
            "End",
            min_value=0.0,
            max_value=100.0,
            step=0.001,
            value=100.0,
            format="%.3f",
        )

    filtered_df = filtered_df[filtered_df["percentile"].between(start, end)]

    yaxis_type = st.selectbox("Select a y-axis type", ["linear", "log"])

    # Display detailed plot
    fig = create_detailed_plot(filtered_df, variable, year, yaxis_type, meta)
    st.plotly_chart(fig, use_container_width=True)


def load_countries():
    """Load the countries data from CSV."""
    return pd.read_csv("wid_all_data/WID_countries.csv", sep=";")


def load_country_data(country_code):
    """Load country-specific data and metadata."""
    df = pd.read_csv(f"wid_all_data/WID_data_{country_code}.csv", sep=";")
    meta = pd.read_csv(f"wid_all_data/WID_metadata_{country_code}.csv", sep=";")
    return df, meta


def parse_percentile(x):
    """Parse percentile string like 'p50p90' into tuple (50, 90)."""
    return tuple(map(float, x.strip("p").split("p")))


def format_variable(v, meta):
    """Format variable name with description columns."""
    desc_cols = ["shortname", "shorttype", "shortpop", "shortage", "unit"]
    return " | ".join(map(str, meta[meta["variable"] == v][desc_cols].values[0]))


def get_locale(country_code, currency):
    """Get locale for formatting currency based on country code."""
    try:
        language = get_official_languages(country_code)[-1]
        locale = babel.Locale.parse(f"{language}_{country_code}")
    except (IndexError, babel.UnknownLocaleError):
        locale = "en_US"
    return locale


def get_currency_conversion_rate(currency):
    """Get USD to currency conversion rate from API."""
    response = requests.get("https://api.exchangerate-api.com/v4/latest/USD")
    data = response.json()
    return data["rates"][currency]


def get_income_groups():
    """Get income group definitions."""
    return dict(
        key_groups=[
            "p0p100", "p0p50", "p50p90", "p90p99", "p99p100", "p99.99p100",
            # All deciles (p0p10, p10p20, p20p30, …, p90p100)
            *["p{}p{}".format(i * 10, (i + 1) * 10) for i in range(10)],
        ],
        detailed_p_groups=[
            # All percentiles (p0p1, p1p2, …, p98p99, p99p100)
            *["p{}p{}".format(i, i + 1) for i in range(99)],
            # Tenths of a percentile in the top 1%
            "p99p99.1", "p99.1p99.2", "p99.2p99.3", "p99.3p99.4", "p99.4p99.5", "p99.5p99.6", "p99.6p99.7", "p99.7p99.8", "p99.8p99.9",
            #"p99.9p100",
            # Hundreds of a percentile in the top 0.1%
            "p99.9p99.91", "p99.91p99.92", "p99.92p99.93", "p99.93p99.94", "p99.94p99.95", "p99.95p99.96", "p99.96p99.97", "p99.97p99.98", "p99.98p99.99",
            #"p99.99p100",
            # Thousands of a percentile in the top 0.01%
            "p99.99p99.991", "p99.991p99.992", "p99.992p99.993", "p99.993p99.994", "p99.994p99.995", "p99.995p99.996", "p99.996p99.997", "p99.997p99.998", "p99.998p99.999",
            # 10 thousands of a percentile in the top 0.001%
            "p99.999p100",
        ],
        # (p0p100, p1p100, p2p100, …)
        detailed_top_groups=["p{}p100".format(i) for i in range(100)],
    )  # fmt:skip


def filter_data(df, variable, year, group_name):
    """Filter dataframe by variable, year, and income group."""
    groups = get_income_groups()
    df = df[df["variable"] == variable]
    df = df[df["year"] == year]
    df = df[df["percentile"].apply(lambda x: x in groups[group_name])]
    return df


def prepare_summary_data(df, var_meta, country_code, conversion_rate):
    """Prepare summary data for different percentile groups."""
    currency = var_meta["unit"].values[0]
    records = []

    percentile_cutoffs = [
        (1, "Bottom 1%"),
        (5, "Bottom 5%"),
        (10, "Bottom 10%"),
        (50, "Middle 50%"),
        (90, "Top 10%"),
        (95, "Top 5%"),
        (99, "Top 1%"),
        (99.9, "Top 0.1%"),
        (99.99, "Top 0.01%"),
        (99.999, "Top 0.001%"),
    ]

    for cutoff, label in percentile_cutoffs:
        value = int(df[df["percentile"] == cutoff]["value"].values[0])
        locale = get_locale(country_code, currency)
        fmt_local = format_compact_currency(
            value, currency, locale=locale, fraction_digits=1
        )
        value_usd = round(value / conversion_rate)
        fmt_usd = format_compact_currency(
            value_usd, "USD", locale="en_US", fraction_digits=1
        )
        records.append(
            {
                "percentile": label,
                "value_usd": value_usd,
                "usd": fmt_usd,
                "local": fmt_local,
                "afford": get_afford(value_usd),
            }
        )

    return pd.DataFrame.from_records(records)


def create_summary_plot(summary_df, variable, year, meta):
    """Create summary visualization showing income distribution."""
    fig = go.Figure(
        data=[
            go.Scatter(
                x=summary_df["percentile"],
                y=summary_df["value_usd"],
            ),
            go.Bar(
                x=summary_df["percentile"],
                y=summary_df["value_usd"],
            ),
        ]
    )
    fig.update_layout(
        title_text="{} in {}".format(format_variable(variable, meta), year),
        xaxis_title_text="Percentile",
        yaxis_title_text="$ USD",
        showlegend=False,
        margin=dict(l=0, r=0, t=20, b=0),
    )
    return fig


def create_detailed_plot(df, variable, year, yaxis_type, meta):
    """Create detailed visualization with percentile data."""
    fig = go.Figure(
        data=[
            go.Scatter(
                x=df["percentile"],
                y=df["value"],
            ),
            go.Bar(
                x=df["percentile"],
                y=df["value"],
            ),
        ]
    )
    fig.update_layout(
        title_text="{} in {}".format(format_variable(variable, meta), year),
        xaxis_title_text="Percentile",
        yaxis_title_text="Value",
        yaxis_type=yaxis_type,
        yaxis_tickformat=",.0f",
        xaxis=dict(rangeslider=dict(visible=True)),
        yaxis=dict(autorange=True, fixedrange=False),
    )
    return fig


def get_afford(income_usd):
    # try to guess what a person with this income can afford
    match income_usd:
        case n if n <= 0:
            return "☠️"
        case n if n < 100:
            return "nice dinner for two 🍽️"
        case n if n < 200:
            return "pair of Nike shoes 👟"
        case n if n < 300:
            return "weekend hotel stay 🏨"
        case n if n < 500:
            return "budget smartphone 📱"
        case n if n < 750:
            return "round-trip domestic flight ✈️"
        case n if n < 1000:
            return "month's rent in a small town 🏠"
        case n if n < 2000:
            return "gaming console 🎮"
        case n if n < 3000:
            return "high-end laptop 💻"
        case n if n < 5000:
            return "used motorcycle 🏍️"
        case n if n < 7500:
            return "home theater system 📺"
        case n if n < 10000:
            return "semester at community college 🎓"
        case n if n < 25000:
            return "decent used car 🚗"
        case n if n < 35000:
            return "new economy car 🚙"
        case n if n < 50000:
            return "wedding celebration 💒"
        case n if n < 75000:
            return "year at private university 🎓"
        case n if n < 100000:
            return "Tesla Model 3 🚘"
        case n if n < 150000:
            return "mobile home 🏠"
        case n if n < 250000:
            return "small apartment in suburbs 🏢"
        case n if n < 350000:
            return "condo in a major city 🌃"
        case n if n < 500000:
            return "nice house in most cities 🏡"
        case n if n < 750000:
            return "beach house 🏖️"
        case n if n < 1500000:
            return "luxury yacht ⛵"
        case n if n < 2000000:
            return "Bugatti supercar 🏎️"
        case n if n < 3000000:
            return "penthouse apartment 🏙️"
        case n if n < 5000000:
            return "private jet share ✈️"
        case n if n < 7500000:
            return "small vineyard 🍇"
        case n if n < 10000000:
            return "mansion in Beverly Hills 🏰"
        case n if n < 20000000:
            return "private jet ✈️"
        case n if n < 30000000:
            return "luxury hotel 🏨"
        case n if n < 50000000:
            return "private island 🏝️"
        case n if n < 75000000:
            return "minor league sports team ⚾"
        case n if n < 100000000:
            return "professional sports team 🏈"
        case n if n < 200000000:
            return "skyscraper 🏢"
        case n if n < 300000000:
            return "cruise ship 🚢"
        case n if n < 500000000:
            return "space tourism ticket 🚀"
        case n if n < 750000000:
            return "major hospital 🏥"
        case n if n < 1000000000:
            return "satellite constellation 🛰️"
        case n if n < 5000000000:
            return "nuclear power plant ⚡"
        case n if n < 10000000000:
            return "An aircraft carrier 🚢"
        case _:
            return "small country's GDP 🌍"


# Run the app
if __name__ == "__main__":
    main()
