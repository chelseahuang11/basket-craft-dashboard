# Basket Craft Dashboard

**Live app:** https://basket-craft-dashboard-mtldzxhye7ygdgw4vub8jc.streamlit.app/

A Streamlit dashboard connected to a Snowflake data warehouse, built for Basket Craft order analytics.

## Features

- **Headline Metrics** — Total revenue, orders, average order value, and items sold with month-over-month change
- **Revenue Trend** — Daily revenue line chart filterable by date range
- **Top Products by Revenue** — Horizontal bar chart of product revenue (date-filter aware)
- **Bundle Finder** — Pick any product and see which products are most frequently bought together with it, ranked by co-purchase count, with CSV export

## Setup

1. Clone the repo and create a `.env` file with your Snowflake credentials:

```
SNOWFLAKE_ACCOUNT=...
SNOWFLAKE_USER=...
SNOWFLAKE_PASSWORD=...
SNOWFLAKE_ROLE=...
SNOWFLAKE_WAREHOUSE=...
SNOWFLAKE_DATABASE=...
SNOWFLAKE_SCHEMA=...
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run locally:

```bash
streamlit run app.py
```
