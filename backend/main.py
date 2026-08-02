"""QTrader FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qtrader.backend.config import settings
from qtrader.backend.api.data import router as data_router
from qtrader.backend.api.training import router as training_router
from qtrader.backend.api.trading import router as trading_router
from qtrader.backend.api.predict import router as predict_router
from qtrader.backend.api.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    from qtrader.backend.core.data.manager import data_manager
    await data_manager.initialize()

    # Start scheduled minute-data sync (every trading day at 15:30)
    from apscheduler.schedulers.background import BackgroundScheduler
    from qtrader.backend.core.data.minute_sync import start_minute_sync

    scheduler = BackgroundScheduler()

    def _scheduled_minute_sync():
        """Auto sync minute data after market close."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Scheduled minute sync triggered")
        start_minute_sync(market="all", period="1")

    # Run at 15:30 Mon-Fri
    scheduler.add_job(_scheduled_minute_sync, "cron", day_of_week="mon-fri", hour=15, minute=30)
    scheduler.start()

    yield
    # Shutdown
    scheduler.shutdown()
    await data_manager.shutdown()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(data_router, prefix="/api/data", tags=["Data"])
app.include_router(training_router, prefix="/api", tags=["Training"])
app.include_router(trading_router, prefix="/api/trade", tags=["Trading"])
app.include_router(predict_router, prefix="/api/predict", tags=["Predict"])
app.include_router(ws_router, tags=["WebSocket"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": settings.app_version}


def main():
    """Run the server via uvicorn."""
    import uvicorn
    uvicorn.run(
        "qtrader.backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
