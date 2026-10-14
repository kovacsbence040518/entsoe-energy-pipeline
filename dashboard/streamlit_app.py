import streamlit as st
import pandas as pd
import altair as alt

from snowflake.snowpark.context import get_active_session


# Dashboard configuration
st.set_page_config(
    page_title="Energy Market Dashboard",
    layout="wide"
)

st.title("European Energy Market Dashboard")
st.write("Electricity market analysis for Hungary, Austria and Slovakia")

session = get_active_session()



# 1. Daily Electricity Consumption
st.subheader("Daily Electricity Consumption")

daily_load = session.sql("""
    SELECT
        TO_DATE(CONVERT_TIMEZONE('Europe/Budapest', TIMESTAMP)) AS DATE,
        COUNTRY_CODE,
        ROUND(AVG(ACTUAL_LOAD_MW), 2) AS AVG_LOAD_MW
    FROM ENERGY_DB.RAW.LOAD
    GROUP BY DATE, COUNTRY_CODE
    ORDER BY DATE, COUNTRY_CODE
""").to_pandas()

load_chart = daily_load.pivot(
    index="DATE",
    columns="COUNTRY_CODE",
    values="AVG_LOAD_MW"
)

# Shared dashboard filters
selected_countries = st.multiselect(
    "Select countries",
    options=["AT", "HU", "SK"],
    default=["AT", "HU", "SK"]
)

date_range = st.date_input(
    "Select date range",
    value=(load_chart.index.min(), load_chart.index.max()),
    min_value=load_chart.index.min(),
    max_value=load_chart.index.max()
)

if selected_countries and len(date_range) == 2:
    start_date, end_date = date_range

    filtered_load = load_chart.loc[
        (load_chart.index >= start_date) &
        (load_chart.index <= end_date),
        selected_countries
    ]

    if filtered_load.empty:
        st.info("No electricity consumption data available for the selected period.")

    elif len(filtered_load) == 1:
        st.bar_chart(
            filtered_load.T,
            y_label="Average Electricity Load (MW)"
        )

    else:
        st.line_chart(filtered_load)

elif not selected_countries:
    st.info("Please select at least one country.")
else:
    st.info("Please select a start and end date.")



#2. Daily Electricity Prices
st.subheader("Daily Electricity Prices")

daily_prices = session.sql("""
    SELECT
        TO_DATE(CONVERT_TIMEZONE('Europe/Budapest', TIMESTAMP)) AS DATE,
        COUNTRY_CODE,
        ROUND(AVG(PRICE_EUR_MWH), 2) AS AVG_PRICE_EUR_MWH
    FROM ENERGY_DB.RAW.DAY_AHEAD_PRICES
    GROUP BY DATE, COUNTRY_CODE
    ORDER BY DATE, COUNTRY_CODE
""").to_pandas()

price_chart = daily_prices.pivot(
    index="DATE",
    columns="COUNTRY_CODE",
    values="AVG_PRICE_EUR_MWH"
)

if selected_countries and len(date_range) == 2:
    filtered_prices = price_chart.loc[
        (price_chart.index >= start_date) &
        (price_chart.index <= end_date),
        selected_countries
    ]

    if filtered_prices.empty:
        st.info("No electricity price data available for the selected period.")

    elif len(filtered_prices) == 1:
        st.bar_chart(
            filtered_prices.T,
            y_label="Average Electricity Price (EUR/MWh)"
        )

    else:
        st.line_chart(
            filtered_prices,
            y_label="EUR/MWh"
        )


#3. Electricity Generation Mix (MWh)
st.subheader("Electricity Generation Mix")

generation_mix = session.sql("""
    SELECT
        TO_DATE(CONVERT_TIMEZONE('Europe/Budapest', TIMESTAMP)) AS DATE,
        COUNTRY_CODE,
        ENERGY_CATEGORY,
        GENERATION_MW
    FROM ENERGY_DB.ANALYTICS.GENERATION_MIX
""").to_pandas()

if selected_countries and len(date_range) == 2:
    generation_mix["DATE"] = pd.to_datetime(generation_mix["DATE"]).dt.date

    filtered_generation = generation_mix[
        (generation_mix["COUNTRY_CODE"].isin(selected_countries)) &
        (generation_mix["DATE"] >= start_date) &
        (generation_mix["DATE"] <= end_date)
    ]

    # Convert 15-minute average power (MW) into energy (MWh)
    # Energy (MWh) = Power (MW) * 0.25 hours
    if filtered_generation.empty:
        st.info("No electricity generation data available for the selected period.")

        st.subheader("Electricity Generation Mix (%)")
        st.info("No electricity generation data available for the selected period.")

    else:
        generation_summary = (
            filtered_generation
            .groupby(["COUNTRY_CODE", "ENERGY_CATEGORY"])["GENERATION_MW"]
            .sum()
            .mul(0.25)
            .unstack(fill_value=0)
        )

        st.bar_chart(
            generation_summary,
            stack=True,
            y_label="MWh"
        )

        st.subheader("Electricity Generation Mix (%)")

        generation_percentage = generation_summary.div(
            generation_summary.sum(axis=1).replace(0, float("nan")),
            axis=0
        ).mul(100)

        st.bar_chart(
            generation_percentage,
            stack=True,
            y_label="Share (%)"
        )



# 5. Actual vs Forecast Electricity Load
st.subheader("Actual vs Forecast Electricity Load")

forecast_comparison = session.sql("""
    SELECT
        TO_DATE(CONVERT_TIMEZONE('Europe/Budapest', TIMESTAMP)) AS DATE,
        COUNTRY_CODE,
        ROUND(AVG(ACTUAL_LOAD_MW), 2) AS ACTUAL_LOAD_MW,
        ROUND(AVG(FORECAST_LOAD_MW), 2) AS FORECAST_LOAD_MW
    FROM ENERGY_DB.ANALYTICS.LOAD_FORECAST_ANALYSIS
    GROUP BY DATE, COUNTRY_CODE
    ORDER BY DATE, COUNTRY_CODE
""").to_pandas()

forecast_comparison["DATE"] = pd.to_datetime(
    forecast_comparison["DATE"]
).dt.date

if selected_countries and len(date_range) == 2:

    selected_forecast_country = st.selectbox(
        "Select country for forecast comparison",
        options=selected_countries
    )

    filtered_forecast = forecast_comparison[
        (forecast_comparison["COUNTRY_CODE"] == selected_forecast_country) &
        (forecast_comparison["DATE"] >= start_date) &
        (forecast_comparison["DATE"] <= end_date)
    ]

    if filtered_forecast.empty:
        st.info("No actual or forecast load data available for the selected period.")
    else:
        forecast_chart = filtered_forecast.set_index("DATE")[
            ["ACTUAL_LOAD_MW", "FORECAST_LOAD_MW"]
        ]

        forecast_plot = forecast_chart.reset_index().melt(
            id_vars="DATE",
            var_name="TYPE",
            value_name="LOAD_MW"
        )

        min_load = forecast_plot["LOAD_MW"].min() * 0.95
        max_load = forecast_plot["LOAD_MW"].max() * 1.05

        chart = alt.Chart(forecast_plot).mark_line(point=True).encode(
            x=alt.X("DATE:T", title="Date"),
            y=alt.Y(
                "LOAD_MW:Q",
                title="Electricity Load (MW)",
                scale=alt.Scale(
                    domain=[min_load, max_load],
                    zero=False
                )
            ),
            color=alt.Color(
                "TYPE:N",
                title="Load Type",
                legend=alt.Legend(orient="bottom")
            ),
            tooltip=["DATE:T", "TYPE:N", "LOAD_MW:Q"]
        ).properties(height=350)

        st.altair_chart(chart, use_container_width=True)



# 6. Electricity Price vs Consumption
st.subheader("Electricity Price vs Consumption")

if selected_countries and len(date_range) == 2:

    selected_price_country = st.selectbox(
        "Select country for price vs consumption",
        options=selected_countries
    )

    price_load_data = pd.merge(
        daily_load,
        daily_prices,
        on=["DATE", "COUNTRY_CODE"],
        how="inner"
    )

    price_load_data["DATE"] = pd.to_datetime(
        price_load_data["DATE"]
    ).dt.date

    filtered_price_load = price_load_data[
        (price_load_data["COUNTRY_CODE"] == selected_price_country) &
        (price_load_data["DATE"] >= start_date) &
        (price_load_data["DATE"] <= end_date)
    ]

    if filtered_price_load.empty:
        st.info("No electricity price or consumption data available for the selected period.")
    else:

        min_consumption = filtered_price_load["AVG_LOAD_MW"].min() * 0.95
        max_consumption = filtered_price_load["AVG_LOAD_MW"].max() * 1.05

        scatter_plot = alt.Chart(filtered_price_load).mark_circle(
            size=70
        ).encode(
            x=alt.X(
                "AVG_LOAD_MW:Q",
                title="Average Electricity Consumption (MW)",
                scale=alt.Scale(
                    domain=[min_consumption, max_consumption],
                    zero=False
                )
            ),
            y=alt.Y(
                "AVG_PRICE_EUR_MWH:Q",
                title="Average Electricity Price (EUR/MWh)"
            ),
            tooltip=[
                "DATE:T",
                "COUNTRY_CODE:N",
                "AVG_LOAD_MW:Q",
                "AVG_PRICE_EUR_MWH:Q"
            ]
        ).properties(height=350)

        st.altair_chart(scatter_plot, use_container_width=True)