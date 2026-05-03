from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Solboards"
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
    # Lifetime cap per Privy DID. Drain ceiling — once an advertiser has
    # claimed this many USDC across all calls (pending + confirmed), /api/faucet
    # returns 429. Manual override on the VM:
    #   DELETE FROM faucet_claims WHERE advertiser_id='did:privy:...';
    faucet_lifetime_cap_usdc: float = 100.0

    # Comma-separated lists (matching order) of Privy server wallet ids /
    # addresses used to multiplex Circle's 20-USDC-per-2h-per-address devnet
    # faucet limit. Topped up via the manual web faucet, drained back to the
    # treasury via `scripts/sweep_helpers.py`. See PLAN.md Session 12.
    helper_wallet_ids: str = ""
    helper_wallet_addresses: str = ""

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
    # Plays fired per tick are sampled uniformly from [min, max] inclusive.
    # Default is a fixed 1 (min == max) so a missing override keeps the
    # original behavior. Calibrate against the calculator's implied
    # per-second rate (screens × plays/day / 86400) so the dashboard ticks
    # at roughly the rate a real campaign would consume.
    auto_play_plays_per_tick_min: int = 1
    auto_play_plays_per_tick_max: int = 1

    # Comma-separated list of allowed browser origins for CORS. The Vite dev
    # server at 5173 is the only caller today; production will add the real
    # dashboard origin once we deploy (Session 12+).
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # GCS bucket for advertiser-uploaded creatives (Session 13). Bucket has
    # uniform bucket-level access + allUsers:objectViewer so the URL is
    # publicly readable; service account only needs roles/storage.objectCreator.
    # See PLAN.md Session 13 + BUSINESS-CONSTRAINTS.md §5 (creative hosting).
    gcs_bucket_name: str = ""
    gcs_credentials_json: str = ""

    # Hard caps for the upload (re-validated server-side regardless of what the
    # browser claims). 1920x1080 is the demo publisher's only supported format.
    creative_max_bytes: int = 5 * 1024 * 1024
    creative_required_width: int = 1920
    creative_required_height: int = 1080

    # Demo CPM lock + frequency constants (Session 15). The advertiser does not
    # set CPM — it's $0.50 USD = $0.0005/play. Operating hours + plays/hour
    # combine to plays_per_screen_per_day = 144 (12h × 12 plays/h, one play
    # every 5 minutes). Calculator output:
    #   total = screens × plays_per_screen_per_day × days × cpm/1000
    #   protocol_fee = total × protocol_fee_pct
    #   total_to_escrow = total + protocol_fee
    demo_cpm: float = 0.5
    operating_hours_per_day: int = 12
    plays_per_hour_per_screen: int = 12
    protocol_fee_pct: float = 0.025

    # Dedicated Privy server wallet for the 2.5% protocol fee — separate from
    # treasury. Bootstrapped via scripts/bootstrap_protocol_revenue.py.
    # Funded automatically via a Privy tx from each campaign wallet right
    # after x402 settle confirms the budget+fee transfer.
    protocol_revenue_wallet_id: str = ""
    protocol_revenue_wallet_address: str = ""

    # Batch settlement (Session 16.8). /proof writes a `pending` Settlement
    # row and returns sub-100ms; this background loop flushes pending rows
    # every interval, grouping by (campaign, publisher) and emitting one
    # Solana tx per group. Replaces the per-play on-chain settlement that
    # was fragile under RPC rate limits. Disable in tests that want
    # deterministic per-call behavior (e.g. e2e_demo.py).
    batch_enabled: bool = True
    batch_flush_interval_seconds: int = 5
    batch_max_rows_per_flush: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
