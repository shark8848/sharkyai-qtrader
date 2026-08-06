"""Data management API routes."""

from typing import Optional

from fastapi import APIRouter, Query

from qtrader.backend.core.data.manager import data_manager
from qtrader.backend.core.data.qlib_sync import start_sync, get_sync_status
from qtrader.backend.core.data.local_reader import read_local_kline, read_raw_kline
from qtrader.backend.core.data.minute_sync import (
    start_minute_sync,
    get_minute_sync_status,
    get_minute_data,
    get_minute_calendar,
    get_minute_calendar_with_counts,
    get_minute_stocks_for_date,
)
from qtrader.backend.core.data.minute_to_qlib import (
    start_convert,
    get_convert_status,
)

router = APIRouter()


@router.get("/sources")
async def list_sources():
    """List all available data sources and their status."""
    return data_manager.list_sources()


@router.put("/source")
async def switch_source(source_id: str):
    """Switch the active data source."""
    ok = data_manager.switch_source(source_id)
    if not ok:
        return {"error": f"Unknown source: {source_id}"}
    return {"message": f"Switched to {source_id}", "sources": data_manager.list_sources()}


@router.get("/stocks")
async def get_stock_list(keyword: Optional[str] = Query(None, description="Search keyword")):
    """Get stock list, optionally filtered by keyword."""
    df = await data_manager.get_stock_list()
    if keyword and not df.empty:
        mask = df["symbol"].str.contains(keyword, na=False, case=False) | df["name"].str.contains(keyword, na=False)
        df = df[mask]
    records = df.to_dict(orient="records")
    return {"total": len(df), "data": records}


@router.get("/kline/{symbol}")
async def get_kline(
    symbol: str,
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    adjust: str = Query("qfq", description="Adjust mode: qfq/hfq/empty"),
    use_cache: bool = Query(True),
):
    """Get daily kline data for a stock."""
    df = await data_manager.get_daily_kline(symbol, start_date, end_date, adjust, use_cache)
    return {
        "symbol": symbol,
        "rows": len(df),
        "data": df.to_dict(orient="records"),
    }


@router.get("/realtime")
async def get_realtime(symbols: str = Query(..., description="Comma-separated stock codes")):
    """Get realtime quote snapshots."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    df = await data_manager.get_realtime_quote(symbol_list)
    return {"data": df.to_dict(orient="records")}


@router.get("/financial/{symbol}")
async def get_financial(symbol: str):
    """Get financial data for a stock."""
    df = await data_manager.get_financial_data(symbol)
    return {"symbol": symbol, "data": df.to_dict(orient="records")}


@router.post("/sync")
async def sync_data(
    symbol: str,
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    """Force re-sync kline data from the active source (bypass cache)."""
    result = await data_manager.sync_kline(symbol, start_date, end_date)
    return result


@router.post("/sync_qlib")
async def sync_qlib(market: str = Query("all", description="Stock pool to sync")):
    """Start background task: sync AKShare data to Qlib .bin format."""
    result = start_sync(market)
    return result


@router.get("/sync_qlib/status")
async def sync_qlib_status():
    """Get the current sync task progress."""
    return get_sync_status()


# === Minute-level data endpoints ===


@router.post("/sync_minute")
async def sync_minute(
    market: str = Query("all", description="Stock pool"),
    period: str = Query("1", description="Kline period in minutes: 1/5/15/30/60"),
):
    """Start background task: sync minute-level kline data."""
    result = start_minute_sync(market, period)
    return result


@router.get("/sync_minute/status")
async def sync_minute_status():
    """Get minute sync task progress."""
    return get_minute_sync_status()


@router.get("/minute/calendar")
async def minute_calendar(min_stocks: int = Query(0, ge=0)):
    """Get dates that have minute data, with per-date stock counts.

    min_stocks>0 filters out dates with insufficient coverage (e.g. dates
    created by single-stock test syncs that only contain 1~2 files).
    """
    entries = get_minute_calendar_with_counts()
    if min_stocks > 0:
        entries = [e for e in entries if e["count"] >= min_stocks]
    dates = [e["date"] for e in entries]
    return {"dates": dates, "entries": entries, "total": len(dates)}


@router.get("/minute/{symbol}")
async def minute_kline(
    symbol: str,
    date: str = Query(..., description="Date YYYY-MM-DD"),
):
    """Get minute kline data for a stock on a specific date."""
    df = get_minute_data(symbol, date)
    if df is None:
        return {"symbol": symbol, "date": date, "rows": 0, "data": []}
    # Convert datetime to string for JSON
    df = df.copy()
    if "datetime" in df.columns:
        df["datetime"] = df["datetime"].astype(str)
    return {
        "symbol": symbol,
        "date": date,
        "rows": len(df),
        "data": df.to_dict(orient="records"),
    }


@router.get("/minute_stocks/{date}")
async def minute_stocks(date: str):
    """Get list of stocks with minute data for a given date."""
    stocks = get_minute_stocks_for_date(date)
    return {"date": date, "stocks": stocks, "total": len(stocks)}


@router.get("/local_kline/{symbol}")
async def local_kline(symbol: str, days: int = Query(120, ge=1, le=5000)):
    """Read daily kline from local .bin files (no network)."""
    df = read_local_kline(symbol, days)
    return {
        "symbol": symbol,
        "rows": len(df),
        "data": df.to_dict(orient="records") if not df.empty else [],
    }


@router.get("/raw_kline/{symbol}")
async def raw_kline(symbol: str, days: int = Query(120, ge=1, le=5000)):
    """Fetch unadjusted daily kline from akshare (sina, cached 1h)."""
    df = read_raw_kline(symbol, days)
    return {
        "symbol": symbol,
        "rows": len(df),
        "data": df.to_dict(orient="records") if not df.empty else [],
    }


# === Qlib 1min conversion endpoints ===


@router.post("/convert_1min")
async def convert_1min():
    """Convert Parquet minute data to Qlib 1min .bin format."""
    result = start_convert()
    return result


@router.get("/convert_1min/status")
async def convert_1min_status():
    """Get conversion progress."""
    return get_convert_status()
