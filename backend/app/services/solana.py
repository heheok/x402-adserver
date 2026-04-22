"""Solana on-chain helpers: USDC balance reads and USDC-transfer transaction builder.

Privy signs + broadcasts. We construct the bytes.
"""
from __future__ import annotations

import base64

from solana.rpc.async_api import AsyncClient
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.system_program import TransferParams as SystemTransferParams
from solders.system_program import transfer as system_transfer
from solders.transaction import VersionedTransaction
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import (
    TransferCheckedParams,
    create_idempotent_associated_token_account,
    get_associated_token_address,
    transfer_checked,
)

from ..config import get_settings

USDC_DECIMALS = 6


async def get_usdc_balance(owner_address: str) -> float:
    """Read the USDC balance of `owner_address`. Returns 0.0 if the ATA does not exist."""
    settings = get_settings()
    owner = Pubkey.from_string(owner_address)
    mint = Pubkey.from_string(settings.usdc_mint_devnet)
    ata = get_associated_token_address(owner, mint)

    async with AsyncClient(settings.solana_rpc_url) as client:
        try:
            resp = await client.get_token_account_balance(ata)
        except Exception:
            return 0.0
        # solana-py sometimes returns an RPC error object (e.g.
        # `InvalidParamsMessage` when the ATA doesn't exist yet) instead of
        # raising — it has no `.value` attribute.
        value = getattr(resp, "value", None)
        if value is None:
            return 0.0
        return float(value.ui_amount or 0)


async def get_latest_blockhash_str() -> str:
    settings = get_settings()
    async with AsyncClient(settings.solana_rpc_url) as client:
        resp = await client.get_latest_blockhash()
    return str(resp.value.blockhash)


async def build_usdc_transfer_tx(
    from_address: str,
    to_address: str,
    amount_usdc: float,
) -> str:
    """Build a base64-encoded VersionedTransaction that transfers `amount_usdc` USDC.

    The `from_address` is the fee payer and token-account owner. Privy signs with it.
    Creates the destination's USDC ATA idempotently if missing.
    """
    settings = get_settings()
    from_pk = Pubkey.from_string(from_address)
    to_pk = Pubkey.from_string(to_address)
    mint = Pubkey.from_string(settings.usdc_mint_devnet)

    source_ata = get_associated_token_address(from_pk, mint)
    dest_ata = get_associated_token_address(to_pk, mint)
    amount_raw = int(round(amount_usdc * (10 ** USDC_DECIMALS)))

    ata_ix = create_idempotent_associated_token_account(
        payer=from_pk,
        owner=to_pk,
        mint=mint,
    )
    transfer_ix = transfer_checked(
        TransferCheckedParams(
            program_id=TOKEN_PROGRAM_ID,
            source=source_ata,
            mint=mint,
            dest=dest_ata,
            owner=from_pk,
            amount=amount_raw,
            decimals=USDC_DECIMALS,
            signers=[],
        )
    )

    async with AsyncClient(settings.solana_rpc_url) as client:
        bh_resp = await client.get_latest_blockhash()
    blockhash = bh_resp.value.blockhash

    message = MessageV0.try_compile(
        payer=from_pk,
        instructions=[ata_ix, transfer_ix],
        address_lookup_table_accounts=[],
        recent_blockhash=blockhash,
    )
    num_sigs = message.header.num_required_signatures
    tx = VersionedTransaction.populate(message, [Signature.default()] * num_sigs)
    return base64.b64encode(bytes(tx)).decode()


async def build_sol_transfer_tx(
    from_address: str,
    to_address: str,
    lamports: int,
) -> str:
    """Build a base64-encoded VersionedTransaction moving native SOL.

    Used to bootstrap new campaign wallets with enough SOL to pay their own
    fees — RPC devnet airdrops are unreliable, so we transfer from treasury.
    """
    settings = get_settings()
    from_pk = Pubkey.from_string(from_address)
    to_pk = Pubkey.from_string(to_address)

    ix = system_transfer(
        SystemTransferParams(from_pubkey=from_pk, to_pubkey=to_pk, lamports=lamports)
    )

    async with AsyncClient(settings.solana_rpc_url) as client:
        bh_resp = await client.get_latest_blockhash()
    blockhash = bh_resp.value.blockhash

    message = MessageV0.try_compile(
        payer=from_pk,
        instructions=[ix],
        address_lookup_table_accounts=[],
        recent_blockhash=blockhash,
    )
    num_sigs = message.header.num_required_signatures
    tx = VersionedTransaction.populate(message, [Signature.default()] * num_sigs)
    return base64.b64encode(bytes(tx)).decode()


async def airdrop_sol(address: str, sol: float = 1.0) -> str | None:
    """Devnet airdrop for transaction fees. Returns tx signature, or None if unavailable.

    Devnet airdrops are rate-limited and may return an error object instead of a signature.
    Caller should treat a None as "use a web faucet instead."
    """
    settings = get_settings()
    lamports = int(sol * 1_000_000_000)
    async with AsyncClient(settings.solana_rpc_url) as client:
        try:
            resp = await client.request_airdrop(Pubkey.from_string(address), lamports)
        except Exception:
            return None
    value = getattr(resp, "value", None)
    return str(value) if value is not None else None
