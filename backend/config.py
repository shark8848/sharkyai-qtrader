"""QTrader global configuration."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "QTrader"
    app_version: str = "0.1.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Data
    data_dir: str = str(Path.home() / ".qtrader" / "data")
    qlib_data_dir: str = str(Path.home() / ".qlib" / "qlib_data" / "cn_data")
    default_data_source: str = "akshare"

    # Database
    db_url: str = "sqlite+aiosqlite:///" + str(Path.home() / ".qtrader" / "qtrader.db")

    # Job store (training job persistence)
    job_store_backend: str = "sqlite"  # sqlite | postgresql
    job_store_db_path: str = str(Path.home() / ".qtrader" / "jobs.db")
    job_store_pg_dsn: str = ""  # postgresql://user:pass@host:5432/dbname

    # Model store (trained model persistence)
    model_store_dir: str = str(Path.home() / ".qtrader" / "models")

    # Trading
    broker_type: str = "sim"  # sim | eastmoney
    eastmoney_gateway: str = ""
    eastmoney_token: str = ""
    eastmoney_account: str = ""
    eastmoney_password: str = ""

    # Risk management defaults
    max_order_amount: float = 100000.0
    max_daily_trades: int = 50
    max_position_ratio: float = 0.1
    enable_limit_filter: bool = True

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_prefix": "QTRADER_", "env_file": ".env"}


settings = Settings()

# Ensure data directory exists
os.makedirs(settings.data_dir, exist_ok=True)
