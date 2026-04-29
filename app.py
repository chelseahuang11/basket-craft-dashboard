import datetime
import os

import altair as alt
import pandas as pd
import snowflake.connector
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DATA_MIN = datetime.date(2023, 3, 19)
DATA_MAX = datetime.date(2026, 3, 19)

st.title("Basket Craft Dashboard")


def get_connection():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
    )


@st.cache_data(ttl=300)
def load_headline_metrics():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            WITH monthly AS (
                SELECT
                    DATE_TRUNC('month', TO_TIMESTAMP_NTZ(ORDER_CREATED_AT, 9)) AS month,
                    SUM(ORDER_PRICE_USD)  AS revenue,
                    COUNT(*)              AS orders,
                    AVG(ORDER_PRICE_USD)  AS avg_order_value,
                    SUM(ITEMS_PURCHASED)  AS items_sold
                FROM analytics.stg_orders
                GROUP BY 1
                ORDER BY 1 DESC
                LIMIT 2
            )
            SELECT * FROM monthly ORDER BY month DESC
        """)
        return cur.fetchall()


@st.cache_data(ttl=300)
def load_daily_revenue(start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                TO_TIMESTAMP_NTZ(ORDER_CREATED_AT, 9)::DATE AS order_date,
                SUM(ORDER_PRICE_USD)                         AS revenue
            FROM analytics.stg_orders
            WHERE order_date BETWEEN %s AND %s
            GROUP BY 1
            ORDER BY 1
        """, (start_date, end_date))
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["date", "revenue"])


@st.cache_data(ttl=300)
def load_top_products(start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                p.product_name,
                SUM(f.item_price_usd) AS revenue
            FROM analytics.fct_order_items f
            JOIN analytics.dim_products p ON f.product_id = p.product_id
            WHERE TO_TIMESTAMP_NTZ(f.order_date, 9)::DATE BETWEEN %s AND %s
            GROUP BY 1
            ORDER BY 2 DESC
        """, (start_date, end_date))
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["product", "revenue"])


@st.cache_data(ttl=300)
def load_products() -> pd.DataFrame:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT product_id, product_name
            FROM analytics.dim_products
            ORDER BY product_name
        """)
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["product_id", "product_name"])


@st.cache_data(ttl=300)
def load_bundle_data(product_id: int) -> pd.DataFrame:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                p.product_name             AS paired_product,
                COUNT(DISTINCT a.order_id) AS orders_together
            FROM analytics.stg_order_items a
            JOIN analytics.stg_order_items b
                ON  a.order_id   = b.order_id
                AND a.product_id != b.product_id
            JOIN analytics.dim_products p ON b.product_id = p.product_id
            WHERE a.product_id = %s
            GROUP BY 1
            ORDER BY 2 DESC
        """, (product_id,))
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["Paired Product", "Orders Together"])


@st.cache_data(ttl=300)
def smoke_test_row_count():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM analytics.dim_customers")
        return "analytics.dim_customers", cur.fetchone()[0]


def pct_delta(curr, prev):
    if prev and prev != 0:
        return (curr - prev) / abs(prev)
    return None


# ── Headline metrics ──────────────────────────────────────────────────────────
st.subheader("Headline Metrics")
try:
    rows = load_headline_metrics()
    curr, prev = rows[0], rows[1] if len(rows) > 1 else None
    _, curr_rev, curr_orders, curr_aov, curr_items = curr
    _, prev_rev, prev_orders, prev_aov, prev_items = prev if prev else (None,) * 5

    curr_month_label = rows[0][0].strftime("%B %Y")
    cols = st.columns(4)

    with cols[0]:
        delta = pct_delta(curr_rev, prev_rev)
        st.metric("Total Revenue", f"${curr_rev:,.2f}",
                  delta=f"{delta:+.1%}" if delta is not None else None)
    with cols[1]:
        delta = pct_delta(curr_orders, prev_orders)
        st.metric("Total Orders", f"{curr_orders:,}",
                  delta=f"{delta:+.1%}" if delta is not None else None)
    with cols[2]:
        delta = pct_delta(curr_aov, prev_aov)
        st.metric("Avg Order Value", f"${curr_aov:,.2f}",
                  delta=f"{delta:+.1%}" if delta is not None else None)
    with cols[3]:
        delta = pct_delta(curr_items, prev_items)
        st.metric("Items Sold", f"{int(curr_items):,}",
                  delta=f"{delta:+.1%}" if delta is not None else None)

    st.caption(f"Current period: {curr_month_label} vs prior month")

except Exception as e:
    st.error(f"Failed to load metrics: {e}")

st.divider()

# ── Sidebar filters ───────────────────────────────────────────────────────────
default_start = DATA_MAX - datetime.timedelta(days=180)
with st.sidebar:
    st.header("Filters")
    date_range = st.date_input(
        "Date range",
        value=(default_start, DATA_MAX),
        min_value=DATA_MIN,
        max_value=DATA_MAX,
    )

# ── Revenue trend ─────────────────────────────────────────────────────────────
st.subheader("Revenue Trend")

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start, end = date_range
    try:
        df = load_daily_revenue(start, end)
        if df.empty:
            st.info("No orders in the selected date range.")
        else:
            chart = (
                alt.Chart(df)
                .mark_line(point=False, strokeWidth=2)
                .encode(
                    x=alt.X("date:T", title="Date"),
                    y=alt.Y("revenue:Q", title="Revenue (USD)", axis=alt.Axis(format="$,.0f")),
                    tooltip=[
                        alt.Tooltip("date:T", title="Date"),
                        alt.Tooltip("revenue:Q", title="Revenue", format="$,.2f"),
                    ],
                )
                .properties(height=320)
                .interactive()
            )
            st.altair_chart(chart, use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load chart: {e}")
else:
    st.info("Select a start and end date to view the trend.")

# ── Top products ─────────────────────────────────────────────────────────────
st.subheader("Top Products by Revenue")

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    try:
        prod_df = load_top_products(start, end)
        if prod_df.empty:
            st.info("No product data in the selected date range.")
        else:
            bar = (
                alt.Chart(prod_df)
                .mark_bar()
                .encode(
                    x=alt.X("revenue:Q", title="Revenue (USD)", axis=alt.Axis(format="$,.0f")),
                    y=alt.Y("product:N", sort="-x", title=None),
                    tooltip=[
                        alt.Tooltip("product:N", title="Product"),
                        alt.Tooltip("revenue:Q", title="Revenue", format="$,.2f"),
                    ],
                )
                .properties(height=max(120, len(prod_df) * 50))
            )
            st.altair_chart(bar, use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load product chart: {e}")

# ── Bundle finder ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("Bundle Finder")
st.caption("Which products are most often bought together with a given product?")

try:
    products_df = load_products()
    name_to_id = dict(zip(products_df["product_name"], products_df["product_id"]))

    selected_name = st.selectbox("Select a product", options=products_df["product_name"].tolist())
    selected_id = name_to_id[selected_name]

    bundle_df = load_bundle_data(selected_id)
    if bundle_df.empty:
        st.info("No co-purchase data found for this product.")
    else:
        bar = (
            alt.Chart(bundle_df)
            .mark_bar()
            .encode(
                x=alt.X("Orders Together:Q", title="Orders containing both products"),
                y=alt.Y("Paired Product:N", sort="-x", title=None),
                tooltip=[
                    alt.Tooltip("Paired Product:N"),
                    alt.Tooltip("Orders Together:Q", format=","),
                ],
            )
            .properties(height=max(120, len(bundle_df) * 60))
        )
        st.altair_chart(bar, use_container_width=True)

        st.download_button(
            label="Download as CSV",
            data=bundle_df.to_csv(index=False),
            file_name=f"bundles_{selected_name.replace(' ', '_')}.csv",
            mime="text/csv",
        )

except Exception as e:
    st.error(f"Failed to load bundle data: {e}")

# ── Smoke test ────────────────────────────────────────────────────────────────
with st.expander("Snowflake connection check"):
    try:
        table, count = smoke_test_row_count()
        st.success(f"`{table}` — {count:,} rows")
    except Exception as e:
        st.error(f"Connection failed: {e}")
