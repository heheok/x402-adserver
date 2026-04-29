"""Solana on-chain helpers: USDC balance reads and USDC-transfer transaction builder.

Privy signs + broadcasts. We construct the bytes.
"""
from __future__ import annotations

import asyncio
import base64
import time

from solana.rpc.async_api import AsyncClient
from solders.instruction import Instruction
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
# SPL Memo Program v2 — used to attach a unique tag per settlement so two
# concurrent USDC transfers with identical (from, to, amount) still produce
# distinct tx bytes within one blockhash window. Without this, Solana's
# network-level dedup collapses them to a single on-chain tx.
MEMO_PROGRAM_ID = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")


def _memo_ix(memo: str) -> Instruction:
    return Instruction(
        program_id=MEMO_PROGRAM_ID,
        accounts=[],
        data=memo.encode("utf-8"),
    )


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


async def get_sol_balance_lamports(address: str) -> int:
    """Read the native SOL balance (in lamports). Returns 0 on any RPC error."""
    settings = get_settings()
    owner = Pubkey.from_string(address)
    async with AsyncClient(settings.solana_rpc_url) as client:
        try:
            resp = await client.get_balance(owner)
        except Exception:
            return 0
    value = getattr(resp, "value", None)
    if value is None:
        return 0
    return int(value)


async def get_latest_blockhash_str() -> str:
    settings = get_settings()
    async with AsyncClient(settings.solana_rpc_url) as client:
        resp = await client.get_latest_blockhash()
    return str(resp.value.blockhash)


async def build_usdc_transfer_tx(
    from_address: str,
    to_address: str,
    amount_usdc: float,
    memo: str | None = None,
) -> str:
    """Build a base64-encoded VersionedTransaction that transfers `amount_usdc` USDC.

    The `from_address` is the fee payer and token-account owner. Privy signs with it.
    Creates the destination's USDC ATA idempotently if missing.

    Pass `memo` for callers that need byte-unique transactions per call (e.g.
    concurrent settlements with identical from/to/amount). The memo program
    is no-op on-chain but mutates the tx bytes, so Solana's dedup doesn't
    collapse otherwise-identical transfers.
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

    instructions: list[Instruction] = [ata_ix, transfer_ix]
    if memo:
        instructions.append(_memo_ix(memo))

    async with AsyncClient(settings.solana_rpc_url) as client:
        bh_resp = await client.get_latest_blockhash()
    blockhash = bh_resp.value.blockhash

    message = MessageV0.try_compile(
        payer=from_pk,
        instructions=instructions,
        address_lookup_table_accounts=[],
        recent_blockhash=blockhash,
    )
    num_sigs = message.header.num_required_signatures
    tx = VersionedTransaction.populate(message, [Signature.default()] * num_sigs)
    return base64.b64encode(bytes(tx)).decode()


async def build_campaign_bootstrap_tx(
    funder_address: str,
    beneficiary_address: str,
    lamports: int,
) -> str:
    """Build a single tx that seeds SOL AND initializes the USDC ATA.

    Used when the ad server creates a fresh Privy campaign wallet. The
    x402-solana client (browser) refuses to build its transfer tx if the
    destination's USDC ATA doesn't already exist, so we must create it
    server-side before returning 402. Bundling both steps into one tx
    keeps us to a single Privy signAndSend + single confirmation wait.
    """
    settings = get_settings()
    funder_pk = Pubkey.from_string(funder_address)
    beneficiary_pk = Pubkey.from_string(beneficiary_address)
    mint = Pubkey.from_string(settings.usdc_mint_devnet)

    transfer_ix = system_transfer(
        SystemTransferParams(
            from_pubkey=funder_pk, to_pubkey=beneficiary_pk, lamports=lamports
        )
    )
    ata_ix = create_idempotent_associated_token_account(
        payer=funder_pk,
        owner=beneficiary_pk,
        mint=mint,
    )

    async with AsyncClient(settings.solana_rpc_url) as client:
        bh_resp = await client.get_latest_blockhash()
    blockhash = bh_resp.value.blockhash

    message = MessageV0.try_compile(
        payer=funder_pk,
        instructions=[transfer_ix, ata_ix],
        address_lookup_table_accounts=[],
        recent_blockhash=blockhash,
    )
    num_sigs = message.header.num_required_signatures
    tx = VersionedTransaction.populate(message, [Signature.default()] * num_sigs)
    return base64.b64encode(bytes(tx)).decode()


async def get_sol_lamports(address: str) -> int:
    """Read native SOL balance for any address. Returns 0 on RPC error
    (matches `get_usdc_balance`'s defensive shape — the read shouldn't
    fail-fast since callers usually use it for sanity checks)."""
    settings = get_settings()
    try:
        async with AsyncClient(settings.solana_rpc_url) as c:
            resp = await c.get_balance(Pubkey.from_string(address))
        return int(resp.value or 0)
    except Exception:
        return 0


async def get_signature_status(signature: str) -> str | None:
    """One-shot status check for a tx signature, no polling.

    Returns one of: "processed", "confirmed", "finalized", or None if the
    signature isn't visible on-chain. Use this to make a final decision
    after `wait_for_tx_confirmation` times out: if status reached at least
    "processed", the tx is in a block (very likely to confirm) — callers
    should NOT compensate, to avoid the timeout-race double-spend window
    described in PLAN.md Session 16.6 findings.

    Returns None on transient RPC errors (treat as "definitively dead" only
    after a sufficient wait past blockhash expiry).
    """
    settings = get_settings()
    try:
        sig = Signature.from_string(signature)
    except Exception:
        return None
    try:
        async with AsyncClient(settings.solana_rpc_url) as c:
            resp = await c.get_signature_statuses(
                [sig], search_transaction_history=True
            )
    except Exception:
        return None
    value = getattr(resp, "value", None) or []
    s = value[0] if value else None
    if s is None or s.confirmation_status is None:
        return None
    name = str(s.confirmation_status).lower()
    for level in ("finalized", "confirmed", "processed"):
        if level in name:
            return level
    return None


async def wait_for_tx_confirmation(
    signature: str,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 1.0,
) -> bool:
    """Poll getSignatureStatuses until confirmed/finalized or timeout.

    Privy's sign_and_send returns after broadcast, not after finality.
    Callers that need the state to be visible on-chain before their next
    RPC call (e.g. the x402 client fetching the ATA we just created) must
    wait here first. Returns False on timeout; raises on on-chain failure.

    `poll_interval_seconds` controls how often we hit getSignatureStatuses.
    Public devnet RPC limits a single method to 4 req/s/IP — the default 1s
    fits one waiter; concurrent waiters (the batch settler can have several
    in flight at once) should pass 2.0 to halve the per-method rate.
    """
    settings = get_settings()
    sig = Signature.from_string(signature)
    deadline = time.time() + timeout_seconds
    async with AsyncClient(settings.solana_rpc_url) as c:
        while time.time() < deadline:
            try:
                resp = await c.get_signature_statuses(
                    [sig], search_transaction_history=True
                )
            except Exception:
                await asyncio.sleep(poll_interval_seconds)
                continue
            value = getattr(resp, "value", None) or []
            status = value[0] if value else None
            if status is not None and status.confirmation_status is not None:
                name = str(status.confirmation_status).lower()
                if "confirmed" in name or "finalized" in name:
                    if status.err is not None:
                        raise RuntimeError(
                            f"tx {signature} failed on-chain: {status.err}"
                        )
                    return True
            await asyncio.sleep(poll_interval_seconds)
    return False


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
