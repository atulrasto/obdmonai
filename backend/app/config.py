from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database (app role through pgbouncer)
    database_url: str = "postgresql+asyncpg://obdmonai_app:change_me@localhost:5434/obdmonai"
    # Used only by migrations (superuser, direct connection); blank in the backend service
    database_url_direct: str = ""

    # JWT
    jwt_secret_key: str = "change_me_at_least_32_random_chars_for_dev"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # MQTT
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 8883
    mqtt_ca_cert: str = "/mosquitto/certs/ca.crt"
    mqtt_client_cert: str = "/mosquitto/certs/ingest.crt"
    mqtt_client_key: str = "/mosquitto/certs/ingest.key"

    # Anthropic (FleetView, Tier B only)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # Notifications (Tier A alerts + welcome emails)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "alerts@example.com"
    smtp_tls: bool = False      # True = SSL on port 465; False = STARTTLS on port 587
    smtp_to: str = ""          # comma-separated recipient addresses for Tier A alerts
    webhook_url: str = ""      # optional HTTP POST endpoint for alert events

    # Superadmin (platform owner, seeded on startup)
    superadmin_email: str = ""
    superadmin_password: str = ""

    # App
    cell_domain: str = "localhost"   # public hostname for dashboard links in emails
    log_level: str = "INFO"
    environment: str = "development"


settings = Settings()
