from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "x402 Ad Server"
    environment: str = "dev"

    database_url: str = "sqlite:///./data/adserver.db"

    jwt_server_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    proof_context_ttl_seconds: int = 3600  # 1 hour

    publisher_api_key: str = "dev-publisher-key"

    privy_app_id: str = ""
    privy_app_secret: str = ""
    privy_jwks_url: str = "https://auth.privy.io/api/v1/apps/{app_id}/jwks.json"

    solana_rpc_url: str = "https://api.devnet.solana.com"
    usdc_mint_devnet: str = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"

    x402_facilitator_url: str = "https://www.x402.org/facilitator"
    x402_network: str = "solana-devnet"

    treasury_wallet_id: str = ""
    treasury_wallet_address: str = ""
    faucet_amount_usdc: float = 100.0

    # Dev-only default publisher wallet for the "Simulate ad play" button on
    # the dashboard. The same address used in the E2E smoke (Session 5). In
    # production real publishers call /bid + /proof themselves with their own
    # wallets and the simulate endpoint is disabled.
    demo_publisher_wallet: str = "3pMCrwRq5tNy1GdonrPivP389eYjeeoGTiMZDtQmV8W9"

    # Optional demo aid: server-side background loop that randomly picks an
    # active, funded campaign and settles a single play against the demo
    # publisher wallet every `auto_play_interval_seconds`. Off by default —
    # in production real publishers drive /bid + /proof themselves. See
    # `app/services/auto_play.py`.
    auto_play_enabled: bool = False
    auto_play_interval_seconds: int = 15

    # Comma-separated list of allowed browser origins for CORS. The Vite dev
    # server at 5173 is the only caller today; production will add the real
    # dashboard origin once we deploy (Session 12+).
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
