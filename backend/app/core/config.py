"""Application settings loaded from environment variables / .env."""
import logging
import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("foodbridge")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///./foodbridge.db"
    SECRET_KEY: str = ""
    ACCESS_TOKEN_MINUTES: int = 60
    REFRESH_TOKEN_DAYS: int = 7
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Simulated-time multiplier: 60 => one real second equals one simulated minute.
    TIME_SCALE: float = 1.0

    SCHEDULER_ENABLED: bool = True
    SCHEDULER_INTERVAL_SECONDS: float = 30.0

    # Escalation thresholds (simulated minutes since listing creation)
    ESC_T1_MIN: float = 10.0
    ESC_T2_MIN: float = 20.0
    ESC_T3_MIN: float = 30.0
    ESC_MIN_TIME_LEFT_MIN: float = 45.0
    ESC_RADIUS_L0_KM: float = 3.0
    ESC_RADIUS_L1_KM: float = 6.0
    ESC_RADIUS_L2_KM: float = 12.0
    TOP_N_NOTIFY: int = 5

    LOCAL_TZ_OFFSET_MIN: int = 330  # IST; used only for NGO operating-hours and 'today' capacity

    # Safety
    SAFETY_BUFFER: float = 0.15
    HOT_DAY_FACTOR: float = 0.7
    MIN_SAFE_MINUTES: float = 45.0
    EXPIRY_WARNING_MIN: float = 30.0

    # Matching
    AVG_SPEED_KMPH: float = 25.0
    MAX_RADIUS_KM: float = 12.0
    BATCH_RADIUS_KM: float = 3.0  # claims this close to a volunteer's active pickup are batched onto one route

    # Impact
    KG_PER_MEAL: float = 0.4
    CO2E_PER_KG: float = 2.5

    # Abuse limits
    MAX_LISTINGS_PER_DAY: int = 20
    LOGIN_MAX_ATTEMPTS: int = 10
    LOGIN_WINDOW_SECONDS: int = 300
    OTP_MAX_ATTEMPTS: int = 5
    OTP_LOCK_MINUTES: float = 10.0

    MODEL_PATH: str = "./model_artifacts/surplus_model.joblib"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.SECRET_KEY:
        s.SECRET_KEY = secrets.token_urlsafe(48)
        log.warning("SECRET_KEY not set; generated an ephemeral key. Tokens reset on restart.")
    return s


settings = get_settings()
