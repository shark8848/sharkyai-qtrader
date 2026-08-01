"""Data management API routes."""

from typing import Optional

from fastapi import APIRouter, Query

from qtrader.backend.core.data.manager import data_manager

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
        mask = df["symbol"].str.contains(keyword, na=False) | df["name"].str.contains(keyword, na=False)
        df = df[mask]
    records = df.head(200).to_dict(orient="records")
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
