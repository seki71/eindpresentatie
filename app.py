from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(page_title="Washington EV Dashboard", page_icon="⚡", layout="wide")

EV_FILE = Path("Electric_Vehicle_Population_Data.csv")
CHARGING_FILE = Path("EV_Charging_Stations_Feb82024.xlsx")
HISTORY_FILE = Path("Electric_Vehicle_Population_Size_History_By_County.csv")

FOCUS_STATE = "WA"
WA_CENTER_LAT = 47.4
WA_CENTER_LON = -120.7

US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}

# =========================================================
# HELPERS
# =========================================================
def normalize_column_name(name: str) -> str:
    name = str(name).strip().lower()
    name = re.sub(r"[%/]", " ", name)
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name


def clean_text(series: pd.Series, mode: str = "plain") -> pd.Series:
    s = series.astype("string").str.strip()
    s = s.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    if mode == "title":
        return s.str.title()
    if mode == "upper":
        return s.str.upper()
    if mode == "lower":
        return s.str.lower()
    return s


def get_num_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(0)
    return pd.Series(0, index=df.index, dtype="float64")


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    den = den.where(den != 0)
    return num / den


def to_csv_download(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def parse_point_series(series: pd.Series) -> pd.DataFrame:
    extracted = series.astype(str).str.extract(r"POINT\s*\(([-\d\.]+)\s+([-\d\.]+)\)")
    extracted.columns = ["lon", "lat"]
    return extracted.apply(pd.to_numeric, errors="coerce")


def build_region(county: pd.Series, state: pd.Series) -> pd.Series:
    county = county.astype("string")
    state = state.astype("string")
    region = county.fillna("") + ", " + state.fillna("")
    region = region.str.strip(", ").replace({"": pd.NA})
    return region


def clean_state_codes(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip().str.upper()
    s = s.where(s.isin(US_STATE_CODES))
    return s


def coerce_numeric_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


# =========================================================
# LOAD DATA
# =========================================================
@st.cache_data(show_spinner=False)
def load_ev_data() -> pd.DataFrame:
    if not EV_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(EV_FILE, dtype={"Postal Code": "string"}, low_memory=False)
    df.columns = [normalize_column_name(c) for c in df.columns]

    keep_cols = [
        c for c in [
            "postal_code",
            "county",
            "city",
            "state",
            "make",
            "model",
            "model_year",
            "electric_vehicle_type",
            "electric_range",
            "base_msrp",
            "vehicle_location",
        ] if c in df.columns
    ]
    df = df[keep_cols].copy()

    for col, mode in [
        ("county", "title"),
        ("city", "title"),
        ("state", "upper"),
        ("make", "title"),
        ("model", "plain"),
        ("electric_vehicle_type", "plain"),
    ]:
        if col in df.columns:
            df[col] = clean_text(df[col], mode)

    if "state" in df.columns:
        df["state"] = clean_state_codes(df["state"])

    if "postal_code" in df.columns:
        df["postal_code"] = (
            df["postal_code"]
            .astype("string")
            .str.extract(r"(\d{5})", expand=False)
            .str.zfill(5)
        )

    for col in ["model_year", "electric_range", "base_msrp"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "vehicle_location" in df.columns:
        coords = parse_point_series(df["vehicle_location"])
        df = pd.concat([df, coords], axis=1)

    if "lat" in df.columns:
        df.loc[~df["lat"].between(18, 72), "lat"] = pd.NA
    if "lon" in df.columns:
        df.loc[~df["lon"].between(-170, -60), "lon"] = pd.NA

    if "model_year" in df.columns:
        df = df[df["model_year"].fillna(0).between(1990, 2035)].copy()

    if "electric_range" in df.columns:
        df.loc[(df["electric_range"] < 0) | (df["electric_range"] > 1000), "electric_range"] = pd.NA

    if "base_msrp" in df.columns:
        df.loc[(df["base_msrp"] < 0) | (df["base_msrp"] > 250000), "base_msrp"] = pd.NA

    if {"county", "state"}.issubset(df.columns):
        df["region"] = build_region(df["county"], df["state"])
    else:
        df["region"] = pd.NA

    return df.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_charging_data() -> pd.DataFrame:
    if not CHARGING_FILE.exists():
        return pd.DataFrame()

    xls = pd.ExcelFile(CHARGING_FILE)
    preferred_sheet = "Raw" if "Raw" in xls.sheet_names else xls.sheet_names[0]
    df = pd.read_excel(CHARGING_FILE, sheet_name=preferred_sheet)
    df.columns = [normalize_column_name(c) for c in df.columns]

    rename_map = {
        "id": "station_id",
        "station_name": "station_name",
        "ev_network": "ev_network",
        "city": "city",
        "state": "state",
        "zip": "zip",
        "zipcode": "zip",
        "access_code": "access_code",
        "status_code": "status_code",
        "fuel_type_code": "fuel_type_code",
        "latitude": "latitude",
        "longitude": "longitude",
        "ev_level1_evse_num": "ev_level1_evse_num",
        "ev_level2_evse_num": "ev_level2_evse_num",
        "ev_dc_fast_num": "ev_dc_fast_num",
        "ev_dc_fast_count": "ev_dc_fast_num",
        "open_date": "open_date",
        "restricted_access": "restricted_access",
        "facility_type": "facility_type",
        "street_address": "street_address",
    }
    df = df.rename(columns={c: rename_map[c] for c in df.columns if c in rename_map})

    keep_cols = [
        c for c in [
            "station_id",
            "station_name",
            "ev_network",
            "city",
            "state",
            "zip",
            "access_code",
            "status_code",
            "fuel_type_code",
            "latitude",
            "longitude",
            "ev_level1_evse_num",
            "ev_level2_evse_num",
            "ev_dc_fast_num",
            "open_date",
            "restricted_access",
            "facility_type",
            "street_address",
        ] if c in df.columns
    ]
    df = df[keep_cols].copy()

    if "station_id" not in df.columns:
        df["station_id"] = df.index.astype(str)

    for col in ["state", "city", "zip"]:
        if col not in df.columns:
            df[col] = pd.NA

    for col, mode in [
        ("station_name", "plain"),
        ("ev_network", "plain"),
        ("city", "title"),
        ("state", "upper"),
        ("zip", "plain"),
        ("access_code", "lower"),
        ("status_code", "upper"),
        ("fuel_type_code", "upper"),
        ("restricted_access", "lower"),
        ("facility_type", "plain"),
        ("street_address", "plain"),
    ]:
        if col in df.columns:
            df[col] = clean_text(df[col], mode)

    if "state" in df.columns:
        df["state"] = clean_state_codes(df["state"])

    if "zip" in df.columns:
        df["zip"] = (
            df["zip"]
            .astype("string")
            .str.extract(r"(\d{5})", expand=False)
            .str.zfill(5)
        )

    for col in ["latitude", "longitude", "ev_level1_evse_num", "ev_level2_evse_num", "ev_dc_fast_num"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "open_date" in df.columns:
        df["open_date"] = pd.to_datetime(df["open_date"], errors="coerce")

    for col in ["ev_level1_evse_num", "ev_level2_evse_num", "ev_dc_fast_num"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)

    df["l1_ports"] = get_num_series(df, "ev_level1_evse_num")
    df["l2_ports"] = get_num_series(df, "ev_level2_evse_num")
    df["dc_fast_ports"] = get_num_series(df, "ev_dc_fast_num")
    df["usable_port_count"] = df["l2_ports"] + df["dc_fast_ports"]
    df["total_port_count"] = df["l1_ports"] + df["l2_ports"] + df["dc_fast_ports"]

    df["station_type"] = "Level 2 only"
    df.loc[df["dc_fast_ports"] > 0, "station_type"] = "DC Fast"
    df.loc[(df["dc_fast_ports"] > 0) & (df["l2_ports"] > 0), "station_type"] = "Mixed"
    df.loc[
        (df["l1_ports"] > 0) & (df["l2_ports"] == 0) & (df["dc_fast_ports"] == 0),
        "station_type",
    ] = "Level 1 only"

    if "latitude" in df.columns:
        df.loc[~df["latitude"].between(18, 72), "latitude"] = pd.NA
    if "longitude" in df.columns:
        df.loc[~df["longitude"].between(-170, -60), "longitude"] = pd.NA

    return df.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_history_data() -> pd.DataFrame:
    if not HISTORY_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(HISTORY_FILE)
    df.columns = [normalize_column_name(c) for c in df.columns]

    rename_map = {
        "date": "date",
        "county": "county",
        "state": "state",
        "vehicle_primary_use": "vehicle_primary_use",
        "battery_electric_vehicles_bevs": "bevs",
        "plug_in_hybrid_electric_vehicles_phevs": "phevs",
        "electric_vehicle_ev_total": "ev_total",
        "non_electric_vehicle_total": "non_ev_total",
        "total_vehicles": "total_vehicles",
        "percent_electric_vehicles": "percent_ev",
    }
    df = df.rename(columns={c: rename_map[c] for c in df.columns if c in rename_map})

    keep_cols = [
        c for c in [
            "date",
            "county",
            "state",
            "vehicle_primary_use",
            "bevs",
            "phevs",
            "ev_total",
            "non_ev_total",
            "total_vehicles",
            "percent_ev",
        ] if c in df.columns
    ]
    df = df[keep_cols].copy()

    for col, mode in [
        ("county", "title"),
        ("state", "upper"),
        ("vehicle_primary_use", "plain"),
    ]:
        if col in df.columns:
            df[col] = clean_text(df[col], mode)

    if "state" in df.columns:
        df["state"] = clean_state_codes(df["state"])

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in ["bevs", "phevs", "ev_total", "non_ev_total", "total_vehicles", "percent_ev"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.reset_index(drop=True)


# =========================================================
# DERIVED HELPERS
# =========================================================
def infer_county_from_zip(charging_df: pd.DataFrame, ev_df: pd.DataFrame) -> pd.DataFrame:
    out = charging_df.copy()

    if "county" in out.columns and out["county"].notna().any():
        return out

    if "zip" not in out.columns or "postal_code" not in ev_df.columns or "county" not in ev_df.columns:
        out["county"] = pd.NA
        return out

    zip_to_county = (
        ev_df.dropna(subset=["postal_code", "county"])
        .groupby("postal_code")["county"]
        .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else pd.NA)
    )
    out["county"] = out["zip"].map(zip_to_county)
    return out


# =========================================================
# FILTERS
# =========================================================
def filter_ev_data(
    df: pd.DataFrame,
    vehicle_mode: str,
    min_year: str,
    counties: list[str],
    makes: list[str],
    search_term: str,
) -> pd.DataFrame:
    out = df.copy()

    if vehicle_mode == "Alleen BEV" and "electric_vehicle_type" in out.columns:
        out = out[out["electric_vehicle_type"].str.contains("battery", case=False, na=False)]

    if vehicle_mode == "Alleen PHEV" and "electric_vehicle_type" in out.columns:
        out = out[out["electric_vehicle_type"].str.contains("plug", case=False, na=False)]

    if min_year != "Alle jaren" and "model_year" in out.columns:
        out = out[out["model_year"].fillna(0) >= int(min_year)]

    if counties and "county" in out.columns:
        out = out[out["county"].isin(counties)]

    if makes and "make" in out.columns:
        out = out[out["make"].isin(makes)]

    if search_term:
        s = search_term.strip().lower()
        masks = []
        for col in ["county", "city", "postal_code", "make", "model"]:
            if col in out.columns:
                masks.append(out[col].astype("string").str.lower().str.contains(s, na=False))
        if masks:
            combined = masks[0]
            for m in masks[1:]:
                combined = combined | m
            out = out[combined]

    return out.reset_index(drop=True)


def filter_charging_data(
    df: pd.DataFrame,
    access_scope: str,
    port_mode: str,
    zip_search: str,
    search_term: str,
    fast_only: bool,
    recent_mode: str,
    counties: list[str],
) -> pd.DataFrame:
    out = df.copy()

    if "fuel_type_code" in out.columns:
        out = out[out["fuel_type_code"].eq("ELEC")]

    if "status_code" in out.columns:
        out = out[~out["status_code"].isin(["P", "PLANNED"])]

    if access_scope == "Alleen publiek":
        if "access_code" in out.columns:
            out = out[out["access_code"].eq("public")]
        if "restricted_access" in out.columns:
            out = out[~out["restricted_access"].isin(["true", "yes", "1"])]
    elif access_scope == "Publiek + beperkt":
        if "access_code" in out.columns:
            out = out[out["access_code"].eq("public")]

    if fast_only:
        out = out[out["dc_fast_ports"] > 0]

    if recent_mode != "Alle jaren" and "open_date" in out.columns:
        cutoff_year = int(recent_mode)
        out = out[out["open_date"].dt.year >= cutoff_year]

    if counties and "county" in out.columns:
        out = out[out["county"].isin(counties)]

    if zip_search and "zip" in out.columns:
        out = out[out["zip"].astype("string").str.contains(zip_search, na=False)]

    if search_term:
        s = search_term.strip().lower()
        masks = []
        for col in ["county", "city", "zip", "station_name", "street_address", "ev_network"]:
            if col in out.columns:
                masks.append(out[col].astype("string").str.lower().str.contains(s, na=False))
        if masks:
            combined = masks[0]
            for m in masks[1:]:
                combined = combined | m
            out = out[combined]

    out["port_count"] = out["total_port_count"] if port_mode == "Alle poorten" else out["usable_port_count"]
    return out.reset_index(drop=True)


def filter_history_data(
    df: pd.DataFrame,
    counties: list[str],
    search_term: str,
) -> pd.DataFrame:
    out = df.copy()

    if counties and "county" in out.columns:
        out = out[out["county"].isin(counties)]

    if search_term and "county" in out.columns:
        s = search_term.strip().lower()
        out = out[out["county"].astype("string").str.lower().str.contains(s, na=False)]

    return out.reset_index(drop=True)


# =========================================================
# AGGREGATIONS
# =========================================================
def prepare_county_ev_table(ev_df: pd.DataFrame) -> pd.DataFrame:
    if "county" not in ev_df.columns:
        return pd.DataFrame()

    out = (
        ev_df.dropna(subset=["county"])
        .groupby("county", dropna=False)
        .agg(
            ev_count=("county", "size"),
            avg_range=("electric_range", "mean"),
            avg_model_year=("model_year", "mean"),
        )
        .reset_index()
        .sort_values("ev_count", ascending=False)
        .reset_index(drop=True)
    )
    return out


def prepare_zip_table(ev_df: pd.DataFrame, charging_df: pd.DataFrame) -> pd.DataFrame:
    if "postal_code" not in ev_df.columns:
        return pd.DataFrame()

    ev_zip = (
        ev_df.dropna(subset=["postal_code"])
        .groupby("postal_code", dropna=False)
        .agg(
            ev_count=("postal_code", "size"),
            county=("county", lambda x: x.mode().iloc[0] if not x.mode().empty else pd.NA),
            city=("city", lambda x: x.mode().iloc[0] if not x.mode().empty else pd.NA),
            lat=("lat", "median"),
            lon=("lon", "median"),
        )
        .reset_index()
        .rename(columns={"postal_code": "zip"})
    )

    chg_zip = (
        charging_df.dropna(subset=["zip"])
        .groupby("zip", dropna=False)
        .agg(
            station_count=("station_id", "nunique"),
            port_count=("port_count", "sum"),
            l2_ports=("l2_ports", "sum"),
            dc_fast_ports=("dc_fast_ports", "sum"),
        )
        .reset_index()
    )

    merged = ev_zip.merge(chg_zip, on="zip", how="left")
    merged = coerce_numeric_columns(
        merged,
        ["ev_count", "station_count", "port_count", "l2_ports", "dc_fast_ports", "lat", "lon"],
    )

    for col in ["station_count", "port_count", "l2_ports", "dc_fast_ports"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    merged["evs_per_port"] = safe_ratio(merged["ev_count"], merged["port_count"])
    merged["pressure_score"] = merged["ev_count"] / (merged["port_count"] + 1)
    merged["evs_per_port"] = pd.to_numeric(merged["evs_per_port"], errors="coerce")
    merged["pressure_score"] = pd.to_numeric(merged["pressure_score"], errors="coerce").fillna(0)
    merged["zip_label"] = merged["zip"].astype("string")

    return merged.sort_values("pressure_score", ascending=False).reset_index(drop=True)


def prepare_make_table(ev_df: pd.DataFrame) -> pd.DataFrame:
    if not {"make", "model"}.issubset(ev_df.columns):
        return pd.DataFrame()

    return (
        ev_df.dropna(subset=["make", "model"])
        .groupby(["make", "model"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )


def prepare_county_growth_table(history_df: pd.DataFrame, charging_df: pd.DataFrame) -> pd.DataFrame:
    if history_df.empty or "county" not in history_df.columns or "date" not in history_df.columns:
        return pd.DataFrame()

    hist = history_df.copy()

    if "vehicle_primary_use" in hist.columns:
        hist = hist[hist["vehicle_primary_use"].astype("string").str.lower().eq("passenger")].copy()

    hist = hist.dropna(subset=["county", "date", "ev_total"]).copy()
    if hist.empty:
        return pd.DataFrame()

    latest_date = hist["date"].max()
    compare_date = latest_date - pd.DateOffset(years=1)

    latest_df = (
        hist[hist["date"] == latest_date]
        .groupby("county", dropna=False)
        .agg(latest_ev_total=("ev_total", "sum"))
        .reset_index()
    )

    baseline_idx = (
        hist[hist["date"] <= compare_date]
        .sort_values(["county", "date"])
        .groupby("county")["date"]
        .idxmax()
    )

    baseline_df = (
        hist.loc[baseline_idx, ["county", "date", "ev_total"]]
        .rename(columns={"date": "baseline_date", "ev_total": "baseline_ev_total"})
        .reset_index(drop=True)
    )

    growth_df = latest_df.merge(baseline_df, on="county", how="left")
    growth_df["baseline_ev_total"] = pd.to_numeric(growth_df["baseline_ev_total"], errors="coerce").fillna(0)
    growth_df["latest_ev_total"] = pd.to_numeric(growth_df["latest_ev_total"], errors="coerce").fillna(0)
    growth_df["ev_growth_abs"] = growth_df["latest_ev_total"] - growth_df["baseline_ev_total"]
    growth_df["ev_growth_pct"] = safe_ratio(growth_df["ev_growth_abs"], growth_df["baseline_ev_total"]) * 100

    if not charging_df.empty and "county" in charging_df.columns:
        chg_county = (
            charging_df.dropna(subset=["county"])
            .groupby("county", dropna=False)
            .agg(
                station_count=("station_id", "nunique"),
                port_count=("port_count", "sum"),
                dc_fast_ports=("dc_fast_ports", "sum"),
            )
            .reset_index()
        )
    else:
        chg_county = pd.DataFrame(columns=["county", "station_count", "port_count", "dc_fast_ports"])

    growth_df = growth_df.merge(chg_county, on="county", how="left")

    for col in ["station_count", "port_count", "dc_fast_ports"]:
        if col in growth_df.columns:
            growth_df[col] = pd.to_numeric(growth_df[col], errors="coerce").fillna(0)

    growth_df["growth_per_port"] = growth_df["ev_growth_abs"] / (growth_df["port_count"] + 1)
    growth_df["latest_date"] = latest_date

    return growth_df.sort_values("growth_per_port", ascending=False).reset_index(drop=True)


# =========================================================
# DATA
# =========================================================
ev_raw = load_ev_data()
charging_raw = load_charging_data()
history_raw = load_history_data()

if ev_raw.empty:
    st.error("EV-bestand niet gevonden. Zet Electric_Vehicle_Population_Data.csv naast app.py.")
    st.stop()

if charging_raw.empty:
    st.error("Charging-bestand niet gevonden. Zet EV_Charging_Stations_Feb82024.xlsx naast app.py.")
    st.stop()

if "state" in ev_raw.columns:
    ev_raw = ev_raw[ev_raw["state"].eq(FOCUS_STATE)].copy()

if "state" in charging_raw.columns:
    charging_raw = charging_raw[charging_raw["state"].eq(FOCUS_STATE)].copy()

if "state" in history_raw.columns:
    history_raw = history_raw[history_raw["state"].eq(FOCUS_STATE)].copy()

county_options = sorted(ev_raw["county"].dropna().unique().tolist()) if "county" in ev_raw.columns else []
make_options = sorted(ev_raw["make"].dropna().unique().tolist()) if "make" in ev_raw.columns else []
year_values = sorted(ev_raw["model_year"].dropna().astype(int).unique().tolist()) if "model_year" in ev_raw.columns else []

recent_year_choices = ["Alle jaren", "2024", "2022", "2020", "2018", "2015"]
model_year_choices = ["Alle jaren"] + [str(y) for y in sorted(set(year_values), reverse=True)[:15]]

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("Filters — Washington")

    vehicle_mode = st.radio(
        "Voertuigtype",
        ["Alle EV's", "Alleen BEV", "Alleen PHEV"],
        index=0,
    )
    access_scope = st.radio(
        "Laadtoegang",
        ["Alle stations", "Publiek + beperkt", "Alleen publiek"],
        index=0,
    )
    port_mode = st.radio(
        "Poorttelling",
        ["Alle poorten", "Alleen L2 + DC Fast"],
        index=0,
    )

    min_year = st.selectbox("Minimum modeljaar", model_year_choices, index=0)
    recent_mode = st.selectbox("Stations geopend sinds", recent_year_choices, index=0)
    top_n = st.selectbox("Top N", [5, 10, 15, 20, 25], index=1)
    map_limit = st.selectbox("Aantal punten op map", [250, 500, 1000, 1500, 2000], index=2)

    selected_counties = st.multiselect("Counties (EV-data)", county_options)
    selected_makes = st.multiselect("Merken", make_options)
    search_term = st.text_input("Zoeken", placeholder="bijv. King, Seattle, Tesla, 98101")
    zip_search = st.text_input("Filter charging op ZIP", placeholder="bijv. 981")
    fast_only = st.checkbox("Alleen stations met DC Fast", value=False)

# =========================================================
# APPLY FILTERS
# =========================================================
ev_filtered = filter_ev_data(
    ev_raw,
    vehicle_mode=vehicle_mode,
    min_year=min_year,
    counties=selected_counties,
    makes=selected_makes,
    search_term=search_term,
)

charging_with_county = infer_county_from_zip(charging_raw, ev_raw)

charging_filtered = filter_charging_data(
    charging_with_county,
    access_scope=access_scope,
    port_mode=port_mode,
    zip_search=zip_search,
    search_term=search_term,
    fast_only=fast_only,
    recent_mode=recent_mode,
    counties=selected_counties,
)

history_filtered = filter_history_data(
    history_raw,
    counties=selected_counties,
    search_term=search_term,
)

county_ev_table = prepare_county_ev_table(ev_filtered)
zip_table = prepare_zip_table(ev_filtered, charging_filtered)
make_table = prepare_make_table(ev_filtered)
county_growth_table = prepare_county_growth_table(history_filtered, charging_filtered)

port_label = "Poorten" if port_mode == "Alle poorten" else "Poorten (L2+DC)"

# =========================================================
# HEADER
# =========================================================
st.title("⚡ Washington EV Dashboard")
st.caption("Focus op Washington State: EV-populatie, laadstations en infrastructure gap op ZIP- en county-niveau.")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("EV's", f"{len(ev_filtered):,}")
k2.metric("Laadlocaties", f"{charging_filtered['station_id'].nunique():,}")
k3.metric(port_label, f"{int(charging_filtered['port_count'].sum()):,}")
k4.metric("Counties", f"{ev_filtered['county'].dropna().nunique() if 'county' in ev_filtered.columns else 0:,}")

avg_evs_per_port = pd.to_numeric(
    zip_table.get("evs_per_port", pd.Series(dtype=float)),
    errors="coerce",
).dropna().mean()
k5.metric("Gem. EV's / poort", "-" if pd.isna(avg_evs_per_port) else f"{avg_evs_per_port:,.1f}")

active_filters = [f"Staat: {FOCUS_STATE}"]
if selected_counties:
    active_filters.append(f"Counties: {', '.join(selected_counties[:5])}" + ("..." if len(selected_counties) > 5 else ""))
if selected_makes:
    active_filters.append(f"Merken: {', '.join(selected_makes[:5])}" + ("..." if len(selected_makes) > 5 else ""))
if zip_search:
    active_filters.append(f"ZIP filter charging: {zip_search}")
if search_term:
    active_filters.append(f"Zoekterm: {search_term}")
active_filters.append(f"Toegang: {access_scope}")
active_filters.append(f"Poorten: {port_mode}")

st.write(" | ".join(active_filters))

# =========================================================
# TABS
# =========================================================
tab1, tab2, tab3 = st.tabs(["Dashboard", "Groei over tijd", "Data"])

# =========================================================
# TAB 1 - DASHBOARD
# =========================================================
with tab1:
    map_col1, map_col2 = st.columns(2)

    with map_col1:
        st.subheader("Laaddruk per ZIP in Washington")
        map_ev = zip_table.dropna(subset=["lat", "lon"]).copy()

        if len(map_ev) > map_limit:
            map_ev = map_ev.head(map_limit)

        if not map_ev.empty:
            fig_ev_map = px.scatter_map(
                map_ev,
                lat="lat",
                lon="lon",
                size="ev_count",
                color="pressure_score",
                hover_name="zip_label",
                hover_data={
                    "county": True,
                    "city": True,
                    "ev_count": True,
                    "station_count": True,
                    "port_count": True,
                    "lat": False,
                    "lon": False,
                },
                center={"lat": WA_CENTER_LAT, "lon": WA_CENTER_LON},
                zoom=6,
                height=600,
            )
            fig_ev_map.update_layout(
                template="plotly_white",
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig_ev_map, use_container_width=True)
        else:
            st.info("Geen kaartdata beschikbaar voor ZIP-druk in Washington.")

    with map_col2:
        st.subheader("Charging stations in Washington")
        map_chg = charging_filtered.dropna(subset=["latitude", "longitude"]).copy()

        if len(map_chg) > map_limit:
            map_chg = map_chg.sample(map_limit, random_state=42)

        if not map_chg.empty:
            fig_chg_map = px.scatter_map(
                map_chg,
                lat="latitude",
                lon="longitude",
                size="port_count",
                color="station_type",
                hover_name="station_name",
                hover_data={
                    "city": True,
                    "zip": True,
                    "ev_network": True,
                    "port_count": True,
                    "l2_ports": True,
                    "dc_fast_ports": True,
                    "latitude": False,
                    "longitude": False,
                },
                center={"lat": WA_CENTER_LAT, "lon": WA_CENTER_LON},
                zoom=6,
                height=600,
            )
            fig_chg_map.update_layout(
                template="plotly_white",
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig_chg_map, use_container_width=True)
        else:
            st.info("Geen kaartdata beschikbaar voor charging stations.")

    st.markdown("---")

    row1_col1, row1_col2 = st.columns(2)

    with row1_col1:
        if "model_year" in ev_filtered.columns and ev_filtered["model_year"].notna().any():
            hist_df = ev_filtered.dropna(subset=["model_year"]).copy()
            fig_years = px.histogram(
                hist_df,
                x="model_year",
                color="electric_vehicle_type" if "electric_vehicle_type" in hist_df.columns else None,
                nbins=min(30, hist_df["model_year"].nunique()),
                barmode="overlay",
                title="Verdeling van EV's per modeljaar in Washington",
                labels={"model_year": "Modeljaar", "count": "Aantal EV's"},
                template="plotly_white",
            )
            fig_years.update_layout(height=420, bargap=0.05)
            st.plotly_chart(fig_years, use_container_width=True)

    with row1_col2:
        if {"make", "electric_range"}.issubset(ev_filtered.columns):
            top_makes_box = ev_filtered["make"].value_counts(dropna=True).head(8).index.tolist()
            box_df = ev_filtered[
                ev_filtered["make"].isin(top_makes_box)
            ].dropna(subset=["make", "electric_range"]).copy()

            if not box_df.empty:
                fig_range = px.box(
                    box_df,
                    x="make",
                    y="electric_range",
                    color="make",
                    points="outliers",
                    title="Spreiding van actieradius per topmerk",
                    labels={"make": "Merk", "electric_range": "Elektrische range"},
                    template="plotly_white",
                )
                fig_range.update_layout(height=420, showlegend=False)
                st.plotly_chart(fig_range, use_container_width=True)

    row2_col1, row2_col2 = st.columns(2)

    with row2_col1:
        if not county_ev_table.empty:
            treemap_df = county_ev_table.head(top_n).copy()
            fig_county = px.treemap(
                treemap_df,
                path=["county"],
                values="ev_count",
                color="ev_count",
                title="Aandeel EV's per county",
                color_continuous_scale="Blues",
            )
            fig_county.update_layout(height=420, margin=dict(l=0, r=0, t=50, b=0))
            st.plotly_chart(fig_county, use_container_width=True)

    with row2_col2:
        if not zip_table.empty:
            zip_scatter_df = zip_table.dropna(subset=["ev_count", "port_count"]).copy()
            zip_scatter_df = zip_scatter_df[
                (zip_scatter_df["ev_count"] > 0) | (zip_scatter_df["port_count"] > 0)
            ].copy()

            if len(zip_scatter_df) > 250:
                zip_scatter_df = zip_scatter_df.head(250)

            fig_zip_gap = px.scatter(
                zip_scatter_df,
                x="port_count",
                y="ev_count",
                size="pressure_score",
                color="pressure_score",
                hover_name="zip_label",
                hover_data={
                    "county": True,
                    "city": True,
                    "ev_count": True,
                    "station_count": True,
                    "port_count": True,
                    "pressure_score": ":.2f",
                },
                title="Infrastructure gap per ZIP-code",
                labels={
                    "port_count": port_label,
                    "ev_count": "Aantal EV's",
                    "pressure_score": "Drukscore",
                },
                template="plotly_white",
            )
            fig_zip_gap.update_layout(height=420)
            st.plotly_chart(fig_zip_gap, use_container_width=True)

# =========================================================
# TAB 2 - GROEI OVER TIJD
# =========================================================
with tab2:
    st.subheader("EV-groei versus laadinfrastructuur")
    g1, g2, g3 = st.columns(3)

    if not county_growth_table.empty:
        top_growth_county = county_growth_table.iloc[0]["county"]
        top_growth_value = county_growth_table.iloc[0]["growth_per_port"]
        latest_snapshot = county_growth_table["latest_date"].iloc[0]

        g1.metric("Grootste groeiknelpunt", top_growth_county)
        g2.metric("EV-groei per poort", f"{top_growth_value:,.1f}")
        g3.metric("Laatste meetmoment", latest_snapshot.strftime("%Y-%m-%d"))
    else:
        g1.metric("Grootste groeiknelpunt", "-")
        g2.metric("EV-groei per poort", "-")
        g3.metric("Laatste meetmoment", "-")

    growth_col1, growth_col2 = st.columns(2)

    with growth_col1:
        if not county_growth_table.empty:
            top_growth = county_growth_table.head(top_n).sort_values("growth_per_port", ascending=True)
            fig_growth_gap = px.bar(
                top_growth,
                x="growth_per_port",
                y="county",
                orientation="h",
                title="County's waar EV-groei sneller gaat dan laadcapaciteit",
                labels={
                    "growth_per_port": "EV-groei per poort",
                    "county": "",
                },
                template="plotly_white",
            )
            fig_growth_gap.update_layout(height=420)
            st.plotly_chart(fig_growth_gap, use_container_width=True)
        else:
            st.info("Geen historische groeidata beschikbaar.")

    with growth_col2:
        if not county_growth_table.empty:
            scatter_growth = county_growth_table.dropna(subset=["ev_growth_abs", "port_count"]).copy()
            fig_growth_scatter = px.scatter(
                scatter_growth,
                x="port_count",
                y="ev_growth_abs",
                size="latest_ev_total",
                color="growth_per_port",
                hover_name="county",
                hover_data={
                    "baseline_ev_total": True,
                    "latest_ev_total": True,
                    "ev_growth_abs": True,
                    "ev_growth_pct": ":.1f",
                    "station_count": True,
                    "port_count": True,
                    "growth_per_port": ":.2f",
                },
                title="EV-groei per county versus huidige laadcapaciteit",
                labels={
                    "port_count": port_label,
                    "ev_growth_abs": "EV-groei afgelopen jaar",
                    "growth_per_port": "Groei per poort",
                },
                template="plotly_white",
            )
            fig_growth_scatter.update_layout(height=420)
            st.plotly_chart(fig_growth_scatter, use_container_width=True)
        else:
            st.info("Geen historische groeidata beschikbaar.")

    if not county_growth_table.empty:
        st.markdown("### Trend in tijd per county")
        growth_line_df = history_filtered.copy()

        if "vehicle_primary_use" in growth_line_df.columns:
            growth_line_df = growth_line_df[
                growth_line_df["vehicle_primary_use"].astype("string").str.lower().eq("passenger")
            ].copy()

        growth_line_df = growth_line_df.dropna(subset=["county", "date", "ev_total"]).copy()

        if not growth_line_df.empty:
            top_growth_counties = county_growth_table["county"].head(min(top_n, 8)).tolist()
            growth_line_df = growth_line_df[growth_line_df["county"].isin(top_growth_counties)].copy()

            line_df = (
                growth_line_df.groupby(["date", "county"], dropna=False)
                .agg(ev_total=("ev_total", "sum"))
                .reset_index()
            )

            fig_growth_line = px.line(
                line_df,
                x="date",
                y="ev_total",
                color="county",
                title="Ontwikkeling van EV-totaal in counties met grootste groeidruk",
                labels={"date": "Datum", "ev_total": "EV-totaal", "county": "County"},
                template="plotly_white",
            )
            fig_growth_line.update_layout(height=450)
            st.plotly_chart(fig_growth_line, use_container_width=True)

# =========================================================
# TAB 3 - DATA
# =========================================================
with tab3:
    dataset_choice = st.radio(
        "Dataset",
        ["County EV summary", "ZIP gap", "County growth", "Charging stations", "EV records", "History records"],
        horizontal=True,
    )

    if dataset_choice == "County EV summary":
        out_df = county_ev_table.copy()
    elif dataset_choice == "ZIP gap":
        out_df = zip_table.copy()
    elif dataset_choice == "County growth":
        out_df = county_growth_table.copy()
    elif dataset_choice == "Charging stations":
        cols = [
            c for c in [
                "station_name",
                "city",
                "zip",
                "county",
                "access_code",
                "restricted_access",
                "ev_network",
                "station_type",
                "l1_ports",
                "l2_ports",
                "dc_fast_ports",
                "usable_port_count",
                "total_port_count",
                "port_count",
                "open_date",
            ] if c in charging_filtered.columns
        ]
        out_df = charging_filtered[cols].copy()
    elif dataset_choice == "History records":
        cols = [
            c for c in [
                "date",
                "county",
                "vehicle_primary_use",
                "bevs",
                "phevs",
                "ev_total",
                "non_ev_total",
                "total_vehicles",
                "percent_ev",
            ] if c in history_filtered.columns
        ]
        out_df = history_filtered[cols].copy()
    else:
        cols = [
            c for c in [
                "county",
                "city",
                "postal_code",
                "make",
                "model",
                "model_year",
                "electric_vehicle_type",
                "electric_range",
                "base_msrp",
            ] if c in ev_filtered.columns
        ]
        out_df = ev_filtered[cols].copy()

    st.dataframe(out_df.head(1500), use_container_width=True, height=550)

    st.download_button(
        "Download zichtbare tabel CSV",
        to_csv_download(out_df),
        f"{dataset_choice.lower().replace(' ', '_')}.csv",
        "text/csv",
    )