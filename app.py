"""
SET Equity Valuation Tool
Professional dark-theme Streamlit app for Thai stock valuation
Supports: DCF (FCFF), DDM, Relative Valuation, NAV, Sensitivity Analysis, Peer Comparison
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import warnings
import time
import random
warnings.filterwarnings("ignore")

# ─── Rate-limit-safe yfinance wrapper ─────────────────────────────────────────
def _yf_fetch_with_retry(ticker_bk, max_retries=4):
    """
    Fetch yfinance data with exponential backoff + jitter.
    Handles Yahoo Finance 429 / Too Many Requests gracefully.
    """
    for attempt in range(max_retries):
        try:
            # Random small delay before every request (0.3–1.2s)
            time.sleep(random.uniform(0.3, 1.2))
            tk = yf.Ticker(ticker_bk)

            # .info triggers the main API call — wrap separately
            info = {}
            try:
                info = tk.info or {}
            except Exception as e:
                if "429" in str(e) or "Too Many" in str(e):
                    raise e   # let outer handler retry
                info = {}

            # history
            hist = pd.DataFrame()
            try:
                hist = tk.history(period="2y")
            except Exception:
                pass

            # financials  
            financials = balance = cashflow = pd.DataFrame()
            try:
                time.sleep(random.uniform(0.2, 0.6))
                financials = tk.financials
            except Exception:
                pass
            try:
                time.sleep(random.uniform(0.2, 0.6))
                balance = tk.balance_sheet
            except Exception:
                pass
            try:
                time.sleep(random.uniform(0.2, 0.6))
                cashflow = tk.cashflow
            except Exception:
                pass

            return info, hist, financials, balance, cashflow

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Too Many" in err_str or "rate" in err_str.lower():
                wait = (2 ** attempt) + random.uniform(1, 3)   # 2s, 5s, 11s, 19s
                st.warning(f"⏳ Yahoo Finance rate limit hit — waiting {wait:.0f}s before retry {attempt+1}/{max_retries}…")
                time.sleep(wait)
            else:
                raise e

    raise Exception(f"Failed to fetch {ticker_bk} after {max_retries} retries due to rate limiting. Please wait 1–2 minutes and try again.")

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SET Equity Valuation",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Custom CSS (Professional Dark Theme) ─────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

/* ── Base ── */
html, body, [data-testid="stAppViewContainer"] {
    background: #0a0e1a !important;
    color: #e2e8f0 !important;
    font-family: 'IBM Plex Sans', sans-serif;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] { background: #0d1121 !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: #111827;
    border-bottom: 1px solid #1e293b;
    gap: 0;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #64748b;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    padding: 0.75rem 1.25rem;
    border: none;
    border-bottom: 2px solid transparent;
    text-transform: uppercase;
}
.stTabs [aria-selected="true"] {
    color: #38bdf8 !important;
    border-bottom: 2px solid #38bdf8 !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-panel"] {
    padding: 1.5rem 0;
}

/* ── Metric Cards ── */
.metric-card {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
}
.metric-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    letter-spacing: 0.1em;
    color: #64748b;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
}
.metric-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.4rem;
    font-weight: 600;
    color: #f1f5f9;
}
.metric-delta-pos { color: #34d399; font-size: 0.8rem; }
.metric-delta-neg { color: #f87171; font-size: 0.8rem; }

/* ── Header ── */
.app-header {
    background: linear-gradient(135deg, #0f172a 0%, #111827 50%, #0f172a 100%);
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 1.5rem 2rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
}
.app-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.6rem;
    font-weight: 600;
    color: #38bdf8;
    letter-spacing: -0.02em;
    margin: 0;
}
.app-subtitle {
    font-size: 0.85rem;
    color: #64748b;
    margin: 0;
    font-family: 'IBM Plex Sans', sans-serif;
}

/* ── Section Header ── */
.section-header {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    color: #38bdf8;
    text-transform: uppercase;
    border-bottom: 1px solid #1e293b;
    padding-bottom: 0.5rem;
    margin: 1.5rem 0 1rem 0;
}

/* ── DataFrames ── */
[data-testid="stDataFrame"] {
    border: 1px solid #1e293b !important;
    border-radius: 8px !important;
}
.stDataFrame thead tr th {
    background: #1e293b !important;
    color: #94a3b8 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.75rem !important;
}

/* ── Inputs ── */
.stTextInput input, .stNumberInput input {
    background: #111827 !important;
    border: 1px solid #1e293b !important;
    color: #e2e8f0 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    border-radius: 6px !important;
}
.stTextInput input:focus, .stNumberInput input:focus {
    border-color: #38bdf8 !important;
    box-shadow: 0 0 0 2px rgba(56,189,248,0.15) !important;
}
.stSelectbox > div > div {
    background: #111827 !important;
    border: 1px solid #1e293b !important;
    color: #e2e8f0 !important;
}

/* ── Buttons ── */
.stButton > button {
    background: #0369a1 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 6px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.8rem !important;
    letter-spacing: 0.05em !important;
    padding: 0.5rem 1.5rem !important;
    transition: background 0.2s !important;
}
.stButton > button:hover {
    background: #0284c7 !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    background: #111827 !important;
    border: 1px solid #1e293b !important;
    color: #94a3b8 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.8rem !important;
}

/* ── Info / Warning / Error boxes ── */
[data-testid="stAlert"] {
    background: #111827 !important;
    border-left: 3px solid #38bdf8 !important;
}

/* ── Valuation pill ── */
.val-pill {
    display: inline-block;
    background: #0369a1;
    color: #e0f2fe;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    font-weight: 600;
    padding: 0.3rem 0.9rem;
    border-radius: 20px;
    margin: 0.2rem;
}
.val-pill-green {
    background: #065f46;
    color: #d1fae5;
}
.val-pill-red {
    background: #7f1d1d;
    color: #fee2e2;
}

/* ── Football field bar ── */
.ff-container {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 1rem 1.5rem;
    margin: 0.5rem 0;
}
.ff-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #94a3b8;
    letter-spacing: 0.05em;
    margin-bottom: 0.3rem;
}
.ff-bar-wrap {
    position: relative;
    height: 28px;
    background: #1e293b;
    border-radius: 4px;
    margin-bottom: 0.5rem;
}
.ff-bar {
    position: absolute;
    height: 100%;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    font-weight: 600;
    color: white;
}

/* ── Sensitivity table ── */
.sens-table { border-collapse: collapse; width: 100%; font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; }
.sens-table th { background: #1e293b; color: #94a3b8; padding: 0.4rem 0.6rem; text-align: center; }
.sens-table td { padding: 0.35rem 0.6rem; text-align: center; border: 1px solid #1e293b; }
.sens-highlight { background: #0c4a6e; color: #7dd3fc; font-weight: 600; }
.sens-high { background: #064e3b; color: #6ee7b7; }
.sens-low { background: #4c0519; color: #fda4af; }

/* ── Divider ── */
hr { border-color: #1e293b !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0a0e1a; }
::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ─── Session State Init ────────────────────────────────────────────────────────
def init_state():
    defaults = {
        "ticker": "",
        "loaded": False,
        "info": {},
        "hist": None,
        "assumptions": {},
        "wacc_inputs": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ─── Helpers ──────────────────────────────────────────────────────────────────
def fmt_num(v, decimals=1, suffix=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    if abs(v) >= 1e9:
        return f"{v/1e9:.{decimals}f}B{suffix}"
    if abs(v) >= 1e6:
        return f"{v/1e6:.{decimals}f}M{suffix}"
    if abs(v) >= 1e3:
        return f"{v/1e3:.{decimals}f}K{suffix}"
    return f"{v:.{decimals}f}{suffix}"

def safe_get(d, key, default=None):
    v = d.get(key, default)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return default
    return v

def ticker_to_bk(t):
    t = t.strip().upper()
    if not t.endswith(".BK"):
        t = t + ".BK"
    return t

@st.cache_data(ttl=1800, show_spinner=False)   # cache 30 min → fewer repeat calls
def fetch_stock(ticker_bk):
    return _yf_fetch_with_retry(ticker_bk)

def build_assumptions(info, financials, balance, cashflow):
    """Extract last fiscal year actuals + set default projections"""
    yrs = ["Actual", "Y1", "Y2", "Y3", "Y4", "Y5"]

    def _get_is(key, default=0):
        try:
            if key in financials.index:
                return float(financials.loc[key].iloc[0]) if not financials.empty else default
        except:
            pass
        return default

    def _get_bs(key, default=0):
        try:
            if key in balance.index:
                return float(balance.loc[key].iloc[0]) if not balance.empty else default
        except:
            pass
        return default

    def _get_cf(key, default=0):
        try:
            if key in cashflow.index:
                return float(cashflow.loc[key].iloc[0]) if not cashflow.empty else default
        except:
            pass
        return default

    rev = _get_is("Total Revenue") or safe_get(info, "totalRevenue", 1e9)
    cogs = _get_is("Cost Of Revenue") or rev * 0.6
    gross = rev - cogs
    gm = gross / rev if rev else 0.35
    sga_pct = _get_is("Selling General Administrative") / rev if rev else 0.15
    da = _get_is("Reconciled Depreciation") or rev * 0.05
    da_pct = da / rev if rev else 0.05
    ebit = _get_is("EBIT") or rev * 0.12
    interest = abs(_get_is("Interest Expense")) or rev * 0.02
    int_pct = interest / rev if rev else 0.02
    tax_rate = safe_get(info, "effectiveTaxRate", 0.20)
    if tax_rate is None or tax_rate <= 0 or tax_rate > 0.5:
        tax_rate = 0.20
    div = safe_get(info, "dividendsPerShare", 0) or 0
    eps = safe_get(info, "trailingEps", 1) or 1
    payout = (div / eps) if eps and eps > 0 else 0.40

    # Working capital days (rough)
    rec  = _get_bs("Receivables") or rev * 0.10
    inv  = _get_bs("Inventory") or rev * 0.08
    pay  = _get_bs("Payables") or rev * 0.07
    ar_days  = rec / rev * 365 if rev else 45
    inv_days = inv / (rev * (1 - gm)) * 365 if (rev and gm < 1) else 60
    ap_days  = pay / (rev * (1 - gm)) * 365 if (rev and gm < 1) else 45
    capex_pct = abs(_get_cf("Capital Expenditure")) / rev if rev else 0.06

    # Revenue growth assumptions
    rev_growth = [0.0, 0.08, 0.08, 0.07, 0.07, 0.06]

    rows = {}
    rows["Revenue (MB)"]          = [round(rev/1e6, 2)] + [round(rev/1e6 * np.prod([1+rev_growth[j] for j in range(1,i+2)]),2) for i in range(5)]
    rows["Revenue Growth (%)"]    = [0.0] + [g*100 for g in rev_growth[1:]]
    rows["Gross Margin (%)"]      = [round(gm*100,2)] * 6
    rows["SG&A % Rev"]            = [round(sga_pct*100,2)] * 6
    rows["D&A % Rev"]             = [round(da_pct*100,2)] * 6
    rows["Tax Rate (%)"]          = [round(tax_rate*100,2)] * 6
    rows["AR Days"]               = [round(ar_days,1)] * 6
    rows["Inventory Days"]        = [round(inv_days,1)] * 6
    rows["AP Days"]               = [round(ap_days,1)] * 6
    rows["Capex % Rev"]           = [round(capex_pct*100,2)] * 6
    rows["Interest % Rev"]        = [round(int_pct*100,2)] * 6
    rows["Payout Ratio (%)"]      = [round(payout*100,2)] * 6

    df = pd.DataFrame(rows, index=yrs).T
    df.index.name = "Item"
    return df

def compute_IS(df_a):
    """Compute Income Statement from assumptions"""
    results = {}
    cols = df_a.columns.tolist()
    for c in cols:
        rev  = df_a.loc["Revenue (MB)", c]
        gm   = df_a.loc["Gross Margin (%)", c] / 100
        sga  = df_a.loc["SG&A % Rev", c] / 100
        da   = df_a.loc["D&A % Rev", c] / 100
        tax  = df_a.loc["Tax Rate (%)", c] / 100
        int_ = df_a.loc["Interest % Rev", c] / 100
        gross_profit = rev * gm
        sga_abs      = rev * sga
        da_abs       = rev * da
        ebit         = gross_profit - sga_abs - da_abs
        interest_abs = rev * int_
        ebt          = ebit - interest_abs
        taxes        = ebt * tax if ebt > 0 else 0
        net_income   = ebt - taxes
        ebitda       = ebit + da_abs
        results[c] = {
            "Revenue": rev,
            "COGS": rev * (1 - gm),
            "Gross Profit": gross_profit,
            "SG&A": sga_abs,
            "D&A": da_abs,
            "EBIT": ebit,
            "EBITDA": ebitda,
            "Interest Expense": interest_abs,
            "EBT": ebt,
            "Tax": taxes,
            "Net Income": net_income,
        }
    return pd.DataFrame(results)

def compute_BS(df_a, df_is, info):
    """Approximate Balance Sheet projection"""
    cols = df_a.columns.tolist()
    total_debt = safe_get(info, "totalDebt", 0) or 0
    total_assets = safe_get(info, "totalAssets", 0) or 0
    equity = safe_get(info, "bookValue", 0) * safe_get(info, "sharesOutstanding", 1e8) if safe_get(info, "bookValue") else total_assets * 0.4
    results = {}
    prev_ppe = total_assets * 0.4
    prev_equity = equity if equity else 1e6
    for i, c in enumerate(cols):
        rev   = df_is.loc["Revenue", c]
        ar    = rev * df_a.loc["AR Days", c] / 365
        inv   = rev * df_a.loc["Inventory Days", c] / 365
        ap    = rev * df_a.loc["AP Days", c] / 365
        capex = rev * df_a.loc["Capex % Rev", c] / 100
        da    = df_is.loc["D&A", c]
        ni    = df_is.loc["Net Income", c]
        div   = ni * df_a.loc["Payout Ratio (%)", c] / 100
        ppe   = prev_ppe + capex - da
        retained = ni - div
        new_equity = prev_equity + retained
        total_cur_assets = ar + inv + rev * 0.05
        total_non_cur    = ppe
        total_ass        = total_cur_assets + total_non_cur
        total_liab       = total_ass - new_equity
        results[c] = {
            "Cash & Equivalents": rev * 0.05,
            "Accounts Receivable": ar,
            "Inventory": inv,
            "Total Current Assets": total_cur_assets,
            "PP&E (net)": ppe,
            "Total Assets": total_ass,
            "Accounts Payable": ap,
            "Total Debt": total_debt * (1 - i * 0.05),
            "Total Liabilities": total_liab,
            "Shareholders' Equity": new_equity,
            "Total Liab. + Equity": total_ass,
        }
        prev_ppe    = ppe
        prev_equity = new_equity
    return pd.DataFrame(results)

def compute_CF(df_a, df_is):
    """Cash Flow Statement"""
    cols = df_a.columns.tolist()
    results = {}
    for c in cols:
        ni    = df_is.loc["Net Income", c]
        da    = df_is.loc["D&A", c]
        rev   = df_is.loc["Revenue", c]
        ar    = rev * df_a.loc["AR Days", c] / 365
        inv   = rev * df_a.loc["Inventory Days", c] / 365
        ap    = rev * df_a.loc["AP Days", c] / 365
        delta_wc = -(ar + inv - ap) * 0.05  # approx change
        cfo   = ni + da + delta_wc
        capex = -rev * df_a.loc["Capex % Rev", c] / 100
        cfi   = capex
        div   = ni * df_a.loc["Payout Ratio (%)", c] / 100
        cff   = -div
        fcff  = cfo - capex + df_is.loc["Interest Expense", c] * (1 - df_a.loc["Tax Rate (%)", c]/100)
        fcfe  = cfo + capex
        results[c] = {
            "Net Income": ni,
            "D&A (add back)": da,
            "Change in Working Capital": delta_wc,
            "Cash from Operations (CFO)": cfo,
            "Capital Expenditure": capex,
            "Cash from Investing (CFI)": cfi,
            "Dividends Paid": -div,
            "Cash from Financing (CFF)": cff,
            "Net Change in Cash": cfo + cfi + cff,
            "Free Cash Flow to Firm (FCFF)": fcff,
            "Free Cash Flow to Equity (FCFE)": fcfe,
        }
    return pd.DataFrame(results)

def compute_wacc(w):
    ke = w["Rf"] + w["Beta"] * w["ERP"] + w["Size"] + w["Country"]
    kd_at = w["Kd"] * (1 - w["Tax"])
    we = w["WeE"] / 100
    wd = w["WeD"] / 100
    wacc = we * ke + wd * kd_at
    return round(wacc * 100, 4), round(ke * 100, 4), round(kd_at * 100, 4)

def dcf_valuation(df_cf, df_is, wacc_pct, terminal_g, shares_out, total_debt, cash):
    """DCF based on FCFF"""
    wacc = wacc_pct / 100
    tg   = terminal_g / 100
    proj_cols = [c for c in df_cf.columns if c != "Actual"]
    fcffs = [df_cf.loc["Free Cash Flow to Firm (FCFF)", c] for c in proj_cols]
    if not fcffs:
        return None, None
    # Discount
    pv_fcffs = [fcff / (1 + wacc) ** (i + 1) for i, fcff in enumerate(fcffs)]
    last_fcff = fcffs[-1]
    tv = last_fcff * (1 + tg) / (wacc - tg) if wacc > tg else 0
    pv_tv = tv / (1 + wacc) ** len(fcffs)
    ev = sum(pv_fcffs) + pv_tv
    equity_val = ev - total_debt + cash
    price_dcf = equity_val / shares_out if shares_out else 0
    return round(price_dcf, 2), round(ev, 0)

def ddm_valuation(df_is, df_a, wacc_pct, terminal_g, shares_out):
    """Gordon Growth DDM"""
    ke = wacc_pct / 100  # simplify: use WACC as Ke proxy
    tg = terminal_g / 100
    proj_cols = [c for c in df_is.columns if c != "Actual"]
    divs = []
    for c in proj_cols:
        ni  = df_is.loc["Net Income", c]
        pr  = df_a.loc["Payout Ratio (%)", c] / 100
        sh  = shares_out if shares_out else 1
        divs.append(ni * pr / sh)
    if not divs or ke <= tg:
        return None
    pv_divs = [d / (1 + ke) ** (i + 1) for i, d in enumerate(divs)]
    last_div = divs[-1]
    tv = last_div * (1 + tg) / (ke - tg)
    pv_tv = tv / (1 + ke) ** len(divs)
    price_ddm = sum(pv_divs) + pv_tv
    return round(price_ddm, 2)

def relative_valuation(info, df_is, shares_out, df_bs):
    """P/E, EV/EBITDA, P/BV multiples"""
    fwd_pe   = safe_get(info, "forwardPE", None)
    ev_ebit  = safe_get(info, "enterpriseToEbitda", None)
    pb       = safe_get(info, "priceToBook", None)

    # Use Y1 projected figures
    y1 = df_is.columns[1] if len(df_is.columns) > 1 else df_is.columns[0]
    ni_y1    = df_is.loc["Net Income", y1]
    ebitda_y1 = df_is.loc["EBITDA", y1]
    eq_y1    = df_bs.loc["Shareholders' Equity", y1]

    eps_y1   = ni_y1 / shares_out if shares_out else 0
    bv_ps    = eq_y1  / shares_out if shares_out else 0

    results = {}
    if fwd_pe and fwd_pe > 0 and eps_y1:
        results["P/E"] = round(fwd_pe * eps_y1, 2)
    if ev_ebit and ev_ebit > 0 and ebitda_y1:
        total_debt = safe_get(info, "totalDebt", 0) or 0
        cash_      = safe_get(info, "totalCash", 0) or 0
        results["EV/EBITDA"] = round((ev_ebit * ebitda_y1 - total_debt + cash_) / shares_out, 2) if shares_out else None
    if pb and pb > 0 and bv_ps:
        results["P/BV"] = round(pb * bv_ps, 2)
    return results

def sensitivity_table(df_cf, df_is, total_debt, cash, shares_out, wacc_base, tg_base):
    """WACC vs Terminal Growth sensitivity"""
    waccs = [wacc_base - 2, wacc_base - 1, wacc_base, wacc_base + 1, wacc_base + 2]
    tgs   = [tg_base - 1, tg_base - 0.5, tg_base, tg_base + 0.5, tg_base + 1]
    data  = []
    for w in waccs:
        row = []
        for g in tgs:
            p, _ = dcf_valuation(df_cf, df_is, w, g, shares_out, total_debt, cash)
            row.append(round(p, 2) if p else 0)
        data.append(row)
    df = pd.DataFrame(data,
                      index=[f"WACC {w:.1f}%" for w in waccs],
                      columns=[f"g {g:.1f}%" for g in tgs])
    return df, wacc_base, tg_base

# ─── App Header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <div>
    <p class="app-title">◈ SET EQUITY VALUATION</p>
    <p class="app-subtitle">CFA-Framework · DCF · DDM · Relative · NAV · Sensitivity · Peer Comparison</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ─── Ticker Input ─────────────────────────────────────────────────────────────
col_in1, col_in2, col_in3 = st.columns([2, 1, 5])
with col_in1:
    ticker_raw = st.text_input(
        "Ticker (e.g. ICHI, TACC, DELTA)",
        value=st.session_state.get("ticker_raw", ""),
        placeholder="ICHI",
        label_visibility="visible",
    )
with col_in2:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    load_btn = st.button("▶  LOAD", use_container_width=True)

if load_btn and ticker_raw:
    ticker_bk = ticker_to_bk(ticker_raw)
    with st.spinner(f"Fetching {ticker_bk} from Yahoo Finance…"):
        try:
            info, hist, financials, balance, cashflow = fetch_stock(ticker_bk)
            if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
                st.error(f"Cannot find ticker **{ticker_bk}**. Please check the symbol.")
            else:
                st.session_state["ticker_raw"] = ticker_raw
                st.session_state["ticker"]     = ticker_bk
                st.session_state["info"]       = info
                st.session_state["hist"]       = hist
                st.session_state["financials"] = financials
                st.session_state["balance"]    = balance
                st.session_state["cashflow"]   = cashflow
                st.session_state["df_assumptions"] = build_assumptions(info, financials, balance, cashflow)
                # WACC defaults
                beta = safe_get(info, "beta", 1.0) or 1.0
                st.session_state["wacc_inputs"] = {
                    "Rf": 0.025, "Beta": round(beta, 2), "ERP": 0.055,
                    "Size": 0.01, "Country": 0.005,
                    "Kd": 0.045, "Tax": 0.20,
                    "WeE": 70.0, "WeD": 30.0,
                }
                st.session_state["terminal_g"] = 3.0
                st.session_state["loaded"] = True
                st.success(f"✓ Loaded {ticker_bk}")
        except Exception as e:
            st.error(f"Error: {e}")

# ─── Main Content (tabs) ──────────────────────────────────────────────────────
if st.session_state["loaded"]:
    info       = st.session_state["info"]
    hist       = st.session_state["hist"]
    financials = st.session_state.get("financials", pd.DataFrame())
    balance    = st.session_state.get("balance", pd.DataFrame())
    cashflow   = st.session_state.get("cashflow", pd.DataFrame())
    ticker_bk  = st.session_state["ticker"]

    price   = safe_get(info, "currentPrice") or safe_get(info, "regularMarketPrice") or 0
    shares  = safe_get(info, "sharesOutstanding") or safe_get(info, "impliedSharesOutstanding") or 1e8
    mktcap  = price * shares
    debt    = safe_get(info, "totalDebt", 0) or 0
    cash_   = safe_get(info, "totalCash", 0) or 0
    ev      = mktcap + debt - cash_
    high52  = safe_get(info, "fiftyTwoWeekHigh", 0) or 0
    low52   = safe_get(info, "fiftyTwoWeekLow", 0) or 0
    beta_v  = safe_get(info, "beta", 1.0) or 1.0
    fwd_pe  = safe_get(info, "forwardPE", None)
    sector  = safe_get(info, "sector", "N/A") or safe_get(info, "industry", "N/A")
    name    = safe_get(info, "longName", ticker_bk) or ticker_bk

    # ── Key Metrics Bar ──
    st.markdown("<div class='section-header'>Key Statistics</div>", unsafe_allow_html=True)
    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    def mcard(col, label, val, delta=None):
        d_html = ""
        if delta is not None:
            cls = "metric-delta-pos" if delta >= 0 else "metric-delta-neg"
            sign = "+" if delta >= 0 else ""
            d_html = f'<div class="{cls}">{sign}{delta:.2f}%</div>'
        col.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{val}</div>
            {d_html}
        </div>""", unsafe_allow_html=True)

    mcard(m1, "Price (THB)", f"฿{price:,.2f}")
    mcard(m2, "Market Cap", fmt_num(mktcap, 1, " ฿"))
    mcard(m3, "EV", fmt_num(ev, 1, " ฿"))
    mcard(m4, "52W High", f"฿{high52:,.2f}")
    mcard(m5, "52W Low", f"฿{low52:,.2f}")
    mcard(m6, "Beta", f"{beta_v:.2f}")
    mcard(m7, "Fwd P/E", f"{fwd_pe:.1f}x" if fwd_pe else "N/A")

    st.markdown(f"<div style='font-size:0.8rem;color:#64748b;margin-bottom:1rem;'>"
                f"<b style='color:#94a3b8'>{name}</b> &nbsp;·&nbsp; {ticker_bk} &nbsp;·&nbsp; {sector}"
                f"</div>", unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tabs = st.tabs([
        "📋 Assumptions",
        "📈 Income Statement",
        "🏦 Balance Sheet",
        "💰 Cash Flow",
        "⚙️ WACC",
        "🎯 Valuation",
        "🔬 Sensitivity",
        "🔭 Peers",
    ])

    # ════════════════════════════════════════════════════════════════════════
    # TAB 0 — ASSUMPTIONS
    # ════════════════════════════════════════════════════════════════════════
    with tabs[0]:
        st.markdown("<div class='section-header'>Financial Assumptions (Edit Below)</div>", unsafe_allow_html=True)
        st.info("All cells are editable. Changes propagate automatically to all other tabs.")

        df_a = st.session_state["df_assumptions"].copy()
        edited = st.data_editor(
            df_a,
            use_container_width=True,
            num_rows="fixed",
            key="assumptions_editor",
        )
        st.session_state["df_assumptions"] = edited

        st.markdown("<div class='section-header'>Terminal Growth Rate</div>", unsafe_allow_html=True)
        tg_col, _ = st.columns([2, 6])
        with tg_col:
            tg = st.number_input("Terminal Growth Rate (%)", value=st.session_state.get("terminal_g", 3.0),
                                  min_value=0.0, max_value=6.0, step=0.25, key="tg_input")
            st.session_state["terminal_g"] = tg

    # ── Compute all statements ───────────────────────────────────────────────
    df_a   = st.session_state["df_assumptions"]
    df_is  = compute_IS(df_a)
    df_bs  = compute_BS(df_a, df_is, info)
    df_cf  = compute_CF(df_a, df_is)
    w_inp  = st.session_state["wacc_inputs"]
    wacc_v, ke_v, kd_at_v = compute_wacc(w_inp)
    tg_v   = st.session_state.get("terminal_g", 3.0)

    def format_df_mb(df):
        return df.style.format("{:,.1f}").set_properties(**{
            'background-color': '#111827',
            'color': '#e2e8f0',
            'font-family': 'IBM Plex Mono, monospace',
            'font-size': '0.82rem',
        })

    # ════════════════════════════════════════════════════════════════════════
    # TAB 1 — INCOME STATEMENT
    # ════════════════════════════════════════════════════════════════════════
    with tabs[1]:
        st.markdown("<div class='section-header'>Income Statement (THB Million)</div>", unsafe_allow_html=True)
        # Color negative rows red, highlight key rows
        styled_is = df_is.copy()
        for col in styled_is.columns:
            styled_is[col] = styled_is[col].apply(lambda x: round(x, 2))
        st.dataframe(styled_is, use_container_width=True)

        # EBITDA margin trend
        st.markdown("<div class='section-header'>Margin Trend</div>", unsafe_allow_html=True)
        margins = pd.DataFrame({
            "Gross Margin (%)":   [df_is.loc["Gross Profit", c] / df_is.loc["Revenue", c] * 100 for c in df_is.columns],
            "EBIT Margin (%)":    [df_is.loc["EBIT", c] / df_is.loc["Revenue", c] * 100 for c in df_is.columns],
            "Net Margin (%)":     [df_is.loc["Net Income", c] / df_is.loc["Revenue", c] * 100 for c in df_is.columns],
            "EBITDA Margin (%)":  [df_is.loc["EBITDA", c] / df_is.loc["Revenue", c] * 100 for c in df_is.columns],
        }, index=df_is.columns)
        st.line_chart(margins, use_container_width=True)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 2 — BALANCE SHEET
    # ════════════════════════════════════════════════════════════════════════
    with tabs[2]:
        st.markdown("<div class='section-header'>Balance Sheet (THB Million)</div>", unsafe_allow_html=True)
        st.dataframe(df_bs.round(2), use_container_width=True)
        # Leverage chart
        st.markdown("<div class='section-header'>Leverage</div>", unsafe_allow_html=True)
        lev = pd.DataFrame({
            "Total Debt": [df_bs.loc["Total Debt", c] for c in df_bs.columns],
            "Equity":     [df_bs.loc["Shareholders' Equity", c] for c in df_bs.columns],
        }, index=df_bs.columns)
        st.bar_chart(lev, use_container_width=True)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 3 — CASH FLOW
    # ════════════════════════════════════════════════════════════════════════
    with tabs[3]:
        st.markdown("<div class='section-header'>Cash Flow Statement (THB Million)</div>", unsafe_allow_html=True)
        st.dataframe(df_cf.round(2), use_container_width=True)
        st.markdown("<div class='section-header'>FCFF vs FCFE</div>", unsafe_allow_html=True)
        fcf_chart = pd.DataFrame({
            "FCFF": [df_cf.loc["Free Cash Flow to Firm (FCFF)", c] for c in df_cf.columns],
            "FCFE": [df_cf.loc["Free Cash Flow to Equity (FCFE)", c] for c in df_cf.columns],
        }, index=df_cf.columns)
        st.bar_chart(fcf_chart, use_container_width=True)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 4 — WACC
    # ════════════════════════════════════════════════════════════════════════
    with tabs[4]:
        st.markdown("<div class='section-header'>WACC Inputs</div>", unsafe_allow_html=True)
        w = st.session_state["wacc_inputs"]
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Cost of Equity (CAPM)**")
            w["Rf"]      = st.number_input("Risk-Free Rate (%)",    value=w["Rf"]*100,  step=0.1,  format="%.2f", key="wacc_rf") / 100
            w["Beta"]    = st.number_input("Beta",                  value=w["Beta"],    step=0.05, format="%.2f", key="wacc_b")
            w["ERP"]     = st.number_input("Equity Risk Premium (%)",value=w["ERP"]*100,step=0.1,  format="%.2f", key="wacc_erp") / 100
            w["Size"]    = st.number_input("Size Premium (%)",       value=w["Size"]*100,step=0.1, format="%.2f", key="wacc_size") / 100
            w["Country"] = st.number_input("Country Risk Premium (%)",value=w["Country"]*100,step=0.1,format="%.2f",key="wacc_crp") / 100
        with c2:
            st.markdown("**Cost of Debt**")
            w["Kd"]      = st.number_input("Pre-tax Cost of Debt (%)", value=w["Kd"]*100, step=0.1, format="%.2f", key="wacc_kd") / 100
            w["Tax"]     = st.number_input("Tax Rate (%)",              value=w["Tax"]*100,step=0.5, format="%.2f", key="wacc_tax") / 100
        with c3:
            st.markdown("**Capital Structure**")
            w["WeE"] = st.number_input("Weight of Equity (%)", value=w["WeE"], step=1.0, format="%.1f", key="wacc_we")
            w["WeD"] = st.number_input("Weight of Debt (%)",   value=w["WeD"], step=1.0, format="%.1f", key="wacc_wd")
            if abs(w["WeE"] + w["WeD"] - 100) > 0.1:
                st.warning("⚠ Weights should sum to 100%")
        st.session_state["wacc_inputs"] = w

        wacc_v, ke_v, kd_at_v = compute_wacc(w)
        st.markdown("<div class='section-header'>Result</div>", unsafe_allow_html=True)
        rr1, rr2, rr3 = st.columns(3)
        mcard(rr1, "WACC",           f"{wacc_v:.2f}%")
        mcard(rr2, "Cost of Equity (Ke)", f"{ke_v:.2f}%")
        mcard(rr3, "After-tax Kd",   f"{kd_at_v:.2f}%")

        st.markdown("<div class='section-header'>WACC Decomposition</div>", unsafe_allow_html=True)
        st.markdown(f"""
        | Component | Value |
        |-----------|-------|
        | Rf | {w['Rf']*100:.2f}% |
        | Beta × ERP | {w['Beta']*w['ERP']*100:.2f}% |
        | Size Premium | {w['Size']*100:.2f}% |
        | Country Risk | {w['Country']*100:.2f}% |
        | **Ke** | **{ke_v:.2f}%** |
        | After-tax Kd | {kd_at_v:.2f}% |
        | Weight Equity | {w['WeE']:.1f}% |
        | Weight Debt | {w['WeD']:.1f}% |
        | **WACC** | **{wacc_v:.2f}%** |
        """)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 5 — VALUATION
    # ════════════════════════════════════════════════════════════════════════
    with tabs[5]:
        st.markdown("<div class='section-header'>Intrinsic Value Estimates</div>", unsafe_allow_html=True)

        dcf_price, dcf_ev  = dcf_valuation(df_cf, df_is, wacc_v, tg_v, shares/1e6, debt/1e6, cash_/1e6)
        ddm_price           = ddm_valuation(df_is, df_a, ke_v, tg_v, shares/1e6)
        rel_vals            = relative_valuation(info, df_is, shares/1e6, df_bs)

        vv1, vv2, vv3, vv4 = st.columns(4)
        mcard(vv1, "DCF (FCFF)",    f"฿{dcf_price:,.2f}" if dcf_price else "N/A")
        mcard(vv2, "DDM",            f"฿{ddm_price:,.2f}" if ddm_price else "N/A")
        mcard(vv3, "P/E Target",     f"฿{rel_vals.get('P/E',0):,.2f}" if rel_vals.get("P/E") else "N/A")
        mcard(vv4, "EV/EBITDA Target",f"฿{rel_vals.get('EV/EBITDA',0):,.2f}" if rel_vals.get("EV/EBITDA") else "N/A")

        # Upside/Downside
        st.markdown("<div class='section-header'>Upside / Downside vs Current Price</div>", unsafe_allow_html=True)
        for method, val in [("DCF (FCFF)", dcf_price), ("DDM", ddm_price),
                             ("P/E", rel_vals.get("P/E")), ("EV/EBITDA", rel_vals.get("EV/EBITDA")),
                             ("P/BV", rel_vals.get("P/BV"))]:
            if val and price:
                upside = (val - price) / price * 100
                pill_cls = "val-pill-green" if upside >= 0 else "val-pill-red"
                sign = "▲" if upside >= 0 else "▼"
                st.markdown(
                    f'<span class="val-pill">{method}</span>'
                    f'<span class="val-pill {pill_cls}">{sign} {abs(upside):.1f}%</span>'
                    f'<span style="color:#64748b;font-size:0.8rem;margin-left:0.5rem;">฿{val:,.2f} vs ฿{price:,.2f}</span><br>',
                    unsafe_allow_html=True,
                )

        # Football Field Chart
        st.markdown("<div class='section-header'>Football Field</div>", unsafe_allow_html=True)
        methods_ff = {}
        if dcf_price:
            methods_ff["DCF (FCFF)"] = (dcf_price * 0.85, dcf_price * 1.15, "#0369a1")
        if ddm_price:
            methods_ff["DDM"] = (ddm_price * 0.85, ddm_price * 1.15, "#0891b2")
        if rel_vals.get("P/E"):
            pe_v = rel_vals["P/E"]
            methods_ff["P/E Relative"] = (pe_v * 0.85, pe_v * 1.15, "#0d9488")
        if rel_vals.get("EV/EBITDA"):
            ev_v = rel_vals["EV/EBITDA"]
            methods_ff["EV/EBITDA Rel."] = (ev_v * 0.85, ev_v * 1.15, "#7c3aed")

        if methods_ff:
            all_vals = [v for lo, hi, _ in methods_ff.values() for v in (lo, hi)]
            all_vals.append(price)
            mn, mx = min(all_vals) * 0.9, max(all_vals) * 1.1
            rng = mx - mn if mx != mn else 1

            ff_html = "<div class='ff-container'>"
            for label, (lo, hi, color) in methods_ff.items():
                left_pct  = (lo - mn) / rng * 100
                width_pct = (hi - lo) / rng * 100
                ff_html += f"""
                <div class='ff-label'>{label}</div>
                <div class='ff-bar-wrap'>
                  <div class='ff-bar' style='left:{left_pct:.1f}%;width:{width_pct:.1f}%;background:{color};'>
                    ฿{lo:,.1f} – ฿{hi:,.1f}
                  </div>
                </div>"""
            # Current price marker
            price_pct = (price - mn) / rng * 100
            ff_html += f"""
            <div style='position:relative;height:20px;margin-top:8px;'>
              <div style='position:absolute;left:{price_pct:.1f}%;transform:translateX(-50%);
                  color:#fbbf24;font-family:IBM Plex Mono,monospace;font-size:0.72rem;'>
                ◆ Current ฿{price:,.2f}
              </div>
            </div>
            </div>"""
            st.markdown(ff_html, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 6 — SENSITIVITY
    # ════════════════════════════════════════════════════════════════════════
    with tabs[6]:
        st.markdown("<div class='section-header'>DCF Sensitivity — WACC vs Terminal Growth Rate</div>", unsafe_allow_html=True)
        sens_df, _, _ = sensitivity_table(df_cf, df_is, debt/1e6, cash_/1e6, shares/1e6, wacc_v, tg_v)

        # Build colored HTML table
        mid_wacc_idx = 2
        mid_tg_idx   = 2
        html_rows = "<table class='sens-table'><tr><th>WACC \\ g</th>"
        for col in sens_df.columns:
            html_rows += f"<th>{col}</th>"
        html_rows += "</tr>"
        for r_i, (idx, row) in enumerate(sens_df.iterrows()):
            html_rows += f"<tr>"
            html_rows += f"<th>{idx}</th>"
            for c_i, val in enumerate(row):
                cls = ""
                if r_i == mid_wacc_idx and c_i == mid_tg_idx:
                    cls = "sens-highlight"
                elif price and val > price * 1.1:
                    cls = "sens-high"
                elif price and val < price * 0.9:
                    cls = "sens-low"
                html_rows += f"<td class='{cls}'>฿{val:,.2f}</td>"
            html_rows += "</tr>"
        html_rows += "</table>"
        st.markdown(html_rows, unsafe_allow_html=True)
        st.caption("🟦 Base case &nbsp;|&nbsp; 🟩 >10% upside &nbsp;|&nbsp; 🟥 >10% downside vs current price")

        st.markdown("<div class='section-header'>P/E Sensitivity — P/E Multiple vs EPS Growth</div>", unsafe_allow_html=True)
        y1_col = df_is.columns[1] if len(df_is.columns) > 1 else df_is.columns[0]
        base_eps = df_is.loc["Net Income", y1_col] / (shares / 1e6)
        pe_ranges    = [8, 10, 12, 14, 16, 18, 20]
        eps_growths  = [-10, -5, 0, 5, 10, 15, 20]
        pe_data = []
        for pe in pe_ranges:
            row = []
            for g in eps_growths:
                adj_eps = base_eps * (1 + g / 100)
                row.append(round(pe * adj_eps, 2))
            pe_data.append(row)
        pe_sens_df = pd.DataFrame(pe_data,
                                   index=[f"P/E {p}x" for p in pe_ranges],
                                   columns=[f"EPS g {g}%" for g in eps_growths])
        st.dataframe(pe_sens_df, use_container_width=True)

        st.markdown("<div class='section-header'>EV/EBITDA Sensitivity — Multiple vs Revenue Growth</div>", unsafe_allow_html=True)
        base_ebitda_ps = df_is.loc["EBITDA", y1_col] / (shares / 1e6)
        ev_multiples = [4, 6, 8, 10, 12, 14, 16]
        rev_growths  = [-10, -5, 0, 5, 10, 15, 20]
        ev_data = []
        for em in ev_multiples:
            row = []
            for rg in rev_growths:
                adj_ebitda = base_ebitda_ps * (1 + rg / 100)
                ev_adj = em * adj_ebitda * (shares / 1e6) - debt / 1e6 + cash_ / 1e6
                price_implied = ev_adj / (shares / 1e6) if shares else 0
                row.append(round(price_implied, 2))
            ev_data.append(row)
        ev_sens_df = pd.DataFrame(ev_data,
                                   index=[f"EV/EBITDA {m}x" for m in ev_multiples],
                                   columns=[f"Rev g {g}%" for g in rev_growths])
        st.dataframe(ev_sens_df, use_container_width=True)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 7 — PEER COMPARISON
    # ════════════════════════════════════════════════════════════════════════
    with tabs[7]:
        st.markdown("<div class='section-header'>Peer Comparison</div>", unsafe_allow_html=True)
        st.info("Add peer tickers (comma-separated). Thai stocks: omit .BK suffix. Global: use full ticker e.g. AAPL")

        default_peers = ""
        # Auto-suggest peers based on sector
        sector_peers = {
            "Technology": "ADVANC,TRUE,INTUCH,AAPL,MSFT",
            "Financial Services": "KBANK,SCB,BBL,KTB,BAC",
            "Consumer Cyclical": "CPALL,HMPRO,BJC,CRC,ROBINS",
            "Energy": "PTT,PTTEP,BAFS,IRPC,BCP",
            "Healthcare": "BDMS,BH,BCH,CHG,LH",
            "Industrials": "DELTA,HANA,KCEL,KCE,SVI",
            "Real Estate": "CPN,LH,AP,SC,SIRI",
            "Materials": "SCG,SCC,TUF,NWR",
            "Communication Services": "ADVANC,TRUE,DTAC",
            "Consumer Defensive": "TH,OSP,ICHI",
        }
        for s_key, s_peers in sector_peers.items():
            if s_key.lower() in (sector or "").lower():
                default_peers = s_peers
                break

        peers_input = st.text_input("Peer Tickers", value=default_peers, placeholder="KBANK,SCB,AAPL")

        if st.button("🔭  FETCH PEERS"):
            peer_list = [p.strip().upper() for p in peers_input.split(",") if p.strip()]
            peer_list = [ticker_bk] + [ticker_to_bk(p) if not p.endswith(".BK") and "." not in p else p for p in peer_list]
            peer_list = list(dict.fromkeys(peer_list))  # dedupe

            peer_data = []
            prog = st.progress(0)
            status_txt = st.empty()

            def _fetch_peer_info(ptk, retries=3):
                for attempt in range(retries):
                    try:
                        time.sleep(random.uniform(0.8, 2.0))
                        return yf.Ticker(ptk).info or {}
                    except Exception as e:
                        if "429" in str(e) or "Too Many" in str(e):
                            wait = (2 ** attempt) + random.uniform(1, 4)
                            time.sleep(wait)
                        else:
                            return {}
                return {}

            for i, ptk in enumerate(peer_list):
                prog.progress((i + 1) / len(peer_list))
                status_txt.caption(f"Fetching {ptk} ({i+1}/{len(peer_list)})...")
                pi = _fetch_peer_info(ptk)
                if not pi:
                    continue
                try:
                    peer_data.append({
                        "Ticker":     ptk.replace(".BK", ""),
                        "Name":       (pi.get("shortName") or ptk)[:25],
                        "Price":      safe_get(pi, "currentPrice") or safe_get(pi, "regularMarketPrice"),
                        "Mkt Cap (B)": round((safe_get(pi, "marketCap") or 0) / 1e9, 1),
                        "Fwd P/E":   round(safe_get(pi, "forwardPE") or 0, 1) or None,
                        "EV/EBITDA": round(safe_get(pi, "enterpriseToEbitda") or 0, 1) or None,
                        "P/BV":      round(safe_get(pi, "priceToBook") or 0, 2) or None,
                        "ROE (%)":   round((safe_get(pi, "returnOnEquity") or 0) * 100, 1) or None,
                        "Net Margin (%)": round((safe_get(pi, "profitMargins") or 0) * 100, 1) or None,
                        "Div Yield (%)":  round((safe_get(pi, "dividendYield") or 0) * 100, 2) or None,
                        "Beta":       round(safe_get(pi, "beta") or 1, 2),
                    })
                except:
                    pass
            prog.empty()
            status_txt.empty()

            if peer_data:
                peer_df = pd.DataFrame(peer_data)
                # Highlight the target company
                def highlight_target(row):
                    if row["Ticker"] == ticker_bk.replace(".BK", ""):
                        return ["background-color: #0c4a6e; font-weight: bold"] * len(row)
                    return [""] * len(row)
                st.dataframe(
                    peer_df.style.apply(highlight_target, axis=1),
                    use_container_width=True,
                    hide_index=True,
                )

                # Median multiples
                st.markdown("<div class='section-header'>Median Multiples (Peer Universe)</div>", unsafe_allow_html=True)
                num_cols = ["Fwd P/E", "EV/EBITDA", "P/BV", "ROE (%)", "Net Margin (%)", "Div Yield (%)"]
                med_vals = {}
                for nc in num_cols:
                    vals = peer_df[nc].dropna()
                    vals = vals[vals > 0]
                    med_vals[nc] = round(vals.median(), 2) if len(vals) else "N/A"
                med_df = pd.DataFrame([med_vals], index=["Median"])
                st.dataframe(med_df, use_container_width=True)
            else:
                st.warning("No peer data retrieved. Check tickers.")

else:
    # Landing state
    st.markdown("""
    <div style='text-align:center; padding: 4rem 2rem; color:#475569;'>
        <div style='font-size:3rem;margin-bottom:1rem;'>◈</div>
        <div style='font-family:IBM Plex Mono,monospace;font-size:1rem;color:#64748b;letter-spacing:0.1em;'>
            ENTER A SET TICKER ABOVE AND CLICK LOAD
        </div>
        <div style='font-size:0.85rem;margin-top:0.75rem;color:#334155;'>
            Supports all SET-listed stocks · Auto-fetches from Yahoo Finance · Fully editable assumptions
        </div>
    </div>
    """, unsafe_allow_html=True)

# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown("""
<hr/>
<div style='text-align:center;font-family:IBM Plex Mono,monospace;font-size:0.65rem;color:#334155;padding:0.5rem;'>
SET EQUITY VALUATION TOOL &nbsp;·&nbsp; FOR EDUCATIONAL PURPOSES ONLY &nbsp;·&nbsp;
NOT INVESTMENT ADVICE &nbsp;·&nbsp; DATA SOURCE: YAHOO FINANCE
</div>
""", unsafe_allow_html=True)
