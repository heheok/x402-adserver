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

    x402_facilitator_url: str = "https://x402.org/facilitator"
    x402_network: str = "solana-devnet"

    treasury_wallet_id: str = ""
    treasury_wallet_address: str = ""
    faucet_amount_usdc: float = 100.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
