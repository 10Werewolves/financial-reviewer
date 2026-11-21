import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Financial Review", layout="wide")

PCT_METRICS = [
    "Revenue growth", "Gross margin", "EBITDA margin", "Operating margin",
    "Net margin", "FCF margin", "ROE", "ROA",
]


@st.cache_data(ttl=3600, show_spinner=False)
def load(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    return {
        "info": t.info or {},
        "income": t.financials,
        "balance": t.balance_sheet,
        "cash": t.cashflow,
    }


def row(df, *names):
    """Return the first matching line item as a Series, or None."""
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            return df.loc[n].astype(float)
    return None


def div(a, b):
    if a is None or b is None:
        return pd.Series(dtype=float)
    return a / b.replace(0, np.nan)


def compute_ratios(d: dict) -> pd.DataFrame:
    inc, bal, cf = d["income"], d["balance"], d["cash"]

    rev = row(inc, "Total Revenue")
    gp = row(inc, "Gross Profit")
    ebit = row(inc, "EBIT", "Operating Income")
    ebitda = row(inc, "EBITDA", "Normalized EBITDA")
    ni = row(inc, "Net Income")
    intexp = row(inc, "Interest Expense")

    ca = row(bal, "Current Assets")
    cl = row(bal, "Current Liabilities")
    inv = row(bal, "Inventory")
    cash = row(bal, "Cash And Cash Equivalents")
    debt = row(bal, "Total Debt")
    eq = row(bal, "Stockholders Equity", "Common Stock Equity")
    ta = row(bal, "Total Assets")

    fcf = row(cf, "Free Cash Flow")

    quick_num = None
    if ca is not None and inv is not None:
        quick_num = ca - inv.fillna(0)
    net_debt = None
    if debt is not None and cash is not None:
        net_debt = debt - cash

    rev_growth = rev.sort_index().pct_change() if rev is not None else pd.Series(dtype=float)

    data = {
        "Revenue growth": rev_growth,
        "Gross margin": div(gp, rev),
        "EBITDA margin": div(ebitda, rev),
        "Operating margin": div(ebit, rev),
        "Net margin": div(ni, rev),
        "FCF margin": div(fcf, rev),
        "ROE": div(ni, eq),
        "ROA": div(ni, ta),
        "Current ratio": div(ca, cl),
        "Quick ratio": div(quick_num, cl),
        "Debt / Equity": div(debt, eq),
        "Net debt / EBITDA": div(net_debt, ebitda),
        "Interest coverage": div(ebit, intexp.abs() if intexp is not None else None),
        "Asset turnover": div(rev, ta),
    }
    df = pd.DataFrame(data).sort_index().T
    df.columns = [c.year if hasattr(c, "year") else c for c in df.columns]
    return df


def split_ratios(r: pd.DataFrame):
    pct = r.loc[[m for m in PCT_METRICS if m in r.index]] * 100
    mult = r.drop(index=[m for m in PCT_METRICS if m in r.index])
    return pct.round(1), mult.round(2)


def statement_view(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = (df / 1e6).round(1)
    out.columns = [c.year if hasattr(c, "year") else c for c in out.columns]
    return out


def dcf(base_fcf, growth, terminal_g, wacc, years, net_debt, shares):
    flows = [base_fcf * (1 + growth) ** i for i in range(1, years + 1)]
    pv = sum(f / (1 + wacc) ** i for i, f in enumerate(flows, start=1))
    tv = flows[-1] * (1 + terminal_g) / (wacc - terminal_g)
    pv_tv = tv / (1 + wacc) ** years
    ev = pv + pv_tv
    equity = ev - net_debt
    return ev, equity, (equity / shares if shares else None)


st.title("Company Financial Review")
st.caption("Data from Yahoo Finance via yfinance. For learning and screening, not investment advice.")

with st.sidebar:
    st.header("Companies")
    ticker = st.text_input("Primary ticker (e.g. target)", "AAPL").strip().upper()
    compare = st.text_input("Comparison ticker (e.g. acquirer)", "MSFT").strip().upper()

if not ticker:
    st.stop()

try:
    with st.spinner(f"Loading {ticker}..."):
        data = load(ticker)
except Exception as e:
    st.error(f"Could not load {ticker}: {e}")
    st.stop()

if data["income"] is None or data["income"].empty:
    st.error(f"No financial statements found for {ticker}. Check the ticker symbol.")
    st.stop()

info = data["info"]
ratios = compute_ratios(data)

st.subheader(f"{info.get('longName', ticker)} ({ticker})")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Market cap ($B)", f"{info['marketCap'] / 1e9:,.1f}" if info.get("marketCap") else "n/a")
c2.metric("EV ($B)", f"{info['enterpriseValue'] / 1e9:,.1f}" if info.get("enterpriseValue") else "n/a")
c3.metric("EV / EBITDA", f"{info['enterpriseToEbitda']:.1f}x" if info.get("enterpriseToEbitda") else "n/a")
c4.metric("P / E (TTM)", f"{info['trailingPE']:.1f}x" if info.get("trailingPE") else "n/a")
c5.metric("Beta", f"{info['beta']:.2f}" if info.get("beta") else "n/a")

tab_ratios, tab_stmt, tab_chart, tab_dcf, tab_cmp = st.tabs(
    ["Ratios", "Statements", "Trends", "DCF", "Compare"]
)

with tab_ratios:
    pct, mult = split_ratios(ratios)
    st.markdown("**Profitability and growth (%)**")
    st.dataframe(pct, use_container_width=True)
    st.markdown("**Liquidity, leverage, efficiency (x)**")
    st.dataframe(mult, use_container_width=True)

with tab_stmt:
    st.caption("Figures in $ millions (reporting currency).")
    for title, key in [("Income statement", "income"), ("Balance sheet", "balance"), ("Cash flow", "cash")]:
        with st.expander(title, expanded=(key == "income")):
            st.dataframe(statement_view(data[key]), use_container_width=True)

with tab_chart:
    options = list(ratios.index)
    default = [m for m in ["Gross margin", "Operating margin", "Net margin"] if m in options]
    picked = st.multiselect("Metrics", options, default=default)
    if picked:
        plot = ratios.loc[picked].T.reset_index().melt(id_vars="index", var_name="Metric", value_name="Value")
        plot = plot.rename(columns={"index": "Year"}).dropna()
        st.plotly_chart(px.line(plot, x="Year", y="Value", color="Metric", markers=True), use_container_width=True)
    rev = row(data["income"], "Total Revenue")
    ni = row(data["income"], "Net Income")
    if rev is not None:
        base = pd.DataFrame({"Revenue": rev, "Net income": ni}).sort_index() / 1e6
        base.index = [i.year for i in base.index]
        base = base.reset_index().melt(id_vars="index", var_name="Item", value_name="$M")
        st.plotly_chart(px.bar(base, x="index", y="$M", color="Item", barmode="group",
                               labels={"index": "Year"}), use_container_width=True)

with tab_dcf:
    st.markdown("A simplified five-year FCF DCF. Results are very sensitive to the assumptions.")
    fcf_series = row(data["cash"], "Free Cash Flow")
    base_fcf = float(fcf_series.dropna().iloc[0]) if fcf_series is not None and not fcf_series.dropna().empty else 0.0
    a, b, c = st.columns(3)
    growth = a.slider("FCF growth (%/yr)", -10.0, 30.0, 6.0, 0.5) / 100
    wacc = b.slider("Discount rate / WACC (%)", 4.0, 15.0, 9.0, 0.25) / 100
    term_g = c.slider("Terminal growth (%)", 0.0, 5.0, 2.5, 0.25) / 100
    base_fcf_m = st.number_input("Base free cash flow ($M)", value=round(base_fcf / 1e6, 1))
    if wacc <= term_g:
        st.warning("WACC must exceed terminal growth.")
    elif base_fcf_m <= 0:
        st.warning("DCF needs positive base free cash flow.")
    else:
        net_debt = (info.get("totalDebt") or 0) - (info.get("totalCash") or 0)
        shares = info.get("sharesOutstanding")
        ev, equity, per_share = dcf(base_fcf_m * 1e6, growth, term_g, wacc, 5, net_debt, shares)
        d1, d2, d3 = st.columns(3)
        d1.metric("Implied EV ($B)", f"{ev / 1e9:,.1f}")
        d2.metric("Implied equity ($B)", f"{equity / 1e9:,.1f}")
        price = info.get("currentPrice")
        if per_share:
            delta = f"{(per_share / price - 1) * 100:+.1f}% vs market" if price else None
            d3.metric("Implied value / share", f"${per_share:,.2f}", delta)

with tab_cmp:
    if not compare:
        st.info("Enter a comparison ticker in the sidebar.")
    else:
        try:
            other = load(compare)
            other_ratios = compute_ratios(other)
            table = pd.concat(
                [ratios.iloc[:, -1], other_ratios.iloc[:, -1]], axis=1, keys=[ticker, compare]
            )
            pct_rows = [m for m in PCT_METRICS if m in table.index]
            table.loc[pct_rows] = table.loc[pct_rows] * 100
            table = table.round(2)
            table.index = [f"{i} (%)" if i in PCT_METRICS else i for i in table.index]
            st.caption("Most recent fiscal year for each company.")
            st.dataframe(table, use_container_width=True)

            oi = other["info"]
            val = pd.DataFrame({
                ticker: [info.get("marketCap"), info.get("enterpriseValue"), info.get("enterpriseToEbitda"), info.get("trailingPE")],
                compare: [oi.get("marketCap"), oi.get("enterpriseValue"), oi.get("enterpriseToEbitda"), oi.get("trailingPE")],
            }, index=["Market cap", "Enterprise value", "EV / EBITDA", "P / E"])
            st.dataframe(val, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load {compare}: {e}")
