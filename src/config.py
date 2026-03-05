"""Configuration module for CAME API Sniffer.

Loads configuration from .env file using python-dotenv, with sensible defaults.
All components access configuration through the global Config instance.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration."""

    # Server CAME target
    came_host: str
    came_port: int

    # Proxy
    proxy_port: int

    # Dashboard
    dashboard_port: int

    # Storage
    data_dir: str
    db_name: str

    # Logging
    log_level: str


def load_config() -> Config:
    """Load configuration from .env file with defaults.

    Returns:
        Config: Validated configuration object.

    Raises:
        ValueError: If required configuration is invalid.
    """
    # Load .env file if it exists
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file)

    # Get configuration values with defaults
    came_host = os.getenv("CAME_HOST", "192.168.x.x")
    came_port_str = os.getenv("CAME_PORT", "80")
    proxy_port_str = os.getenv("PROXY_PORT", "80")
    dashboard_port_str = os.getenv("DASHBOARD_PORT", "8081")
    data_dir = os.getenv("DATA_DIR", "./data")
    db_name = os.getenv("DB_NAME", "came_proxy.db")
    log_level = os.getenv("LOG_LEVEL", "DEBUG")

    # Validate and convert ports
    try:
        came_port = int(came_port_str)
        proxy_port = int(proxy_port_str)
        dashboard_port = int(dashboard_port_str)
    except ValueError as e:
        raise ValueError(f"Invalid port configuration: {e}")

    # Validate port ranges
    for port, name in [
        (came_port, "CAME_PORT"),
        (proxy_port, "PROXY_PORT"),
        (dashboard_port, "DASHBOARD_PORT"),
    ]:
        if not 1 <= port <= 65535:
            raise ValueError(f"{name} must be between 1 and 65535, got {port}")

    # Validate log level
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level.upper() not in valid_levels:
        raise ValueError(f"LOG_LEVEL must be one of {valid_levels}, got {log_level}")

    return Config(
        came_host=came_host,
        came_port=came_port,
        proxy_port=proxy_port,
        dashboard_port=dashboard_port,
        data_dir=data_dir,
        db_name=db_name,
        log_level=log_level.upper(),
    )


def setup_logging(config: Config) -> logging.Logger:
    """Set up logging for the application.

    Args:
        config: Configuration object.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger("came_proxy")
    logger.setLevel(getattr(logging, config.log_level))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.log_level))

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)

    # Add handler
    logger.addHandler(console_handler)

    return logger


# Global configuration instance (loaded on module import)
try:
    CONFIG = load_config()
    LOGGER = setup_logging(CONFIG)
except Exception as e:
    print(f"Error loading configuration: {e}")
    raise
