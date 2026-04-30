(async () => {
  const WALLETS = [
    "FZ8jbVuRqceNvR8V4RmMtXH7ACx9NzhHb4rFm1qDVJcx",
    "Cw3Wa6u1YXPponj19U7wkpP6diAi4TXAsRjQTU8eKgNu",
    "4FBQMW6zwXitQNXYnuw2N2PyT2bNTpNaRK8UhUAFCMCC",
    "8NWurP1ELBqRAUmX8KcAQVEogXcosvfethYcH6vrsVqt",
    "D4atNw3qRuXUkcKVuzGgosJemP3bboT1B7FSNjHdpjUJ",
  ];
  const NETWORK = "Solana Devnet";
  const PER_WALLET_TIMEOUT = 60_000;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const waitFor = async (fn, ms = 5000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      const v = fn();
      if (v) return v;
      await sleep(100);
    }
    throw new Error("waitFor timeout");
  };
  const findByText = (sel, text) =>
    [...document.querySelectorAll(sel)].find(
      (el) => el.textContent.trim() === text,
    );
  const findSubmit = () =>
    document.querySelector('button[type="submit"].cb-button.primary.w-full');

  const ensureNetwork = async () => {
    const btn = document.querySelector('button[name="network"]');
    if (
      btn.querySelector(".field-display-value")?.textContent.trim() === NETWORK
    )
      return;
    if (btn.getAttribute("aria-expanded") !== "true") btn.click();
    const opt = await waitFor(() =>
      [...document.querySelectorAll('[role="option"]')].find((el) =>
        el.querySelector(`[title="${NETWORK}"]`),
      ),
    );
    ["mousedown", "mouseup", "click"].forEach((t) =>
      opt.dispatchEvent(new MouseEvent(t, { bubbles: true })),
    );
    await waitFor(
      () =>
        btn.querySelector(".field-display-value")?.textContent.trim() ===
        NETWORK,
    );
  };

  const fillWallet = async (addr) => {
    const input =
      document.querySelector(
        'input[name="address"], input[name="walletAddress"], input[name="recipient"]',
      ) || document.querySelector('input[type="text"]:not([name="network"])');
    if (!input) throw new Error("wallet input not found");
    const setter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    ).set;
    setter.call(input, addr);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.dispatchEvent(new Event("blur", { bubbles: true }));
  };

  const clickSubmit = async () => {
    const t0 = Date.now();
    let btn;
    while (Date.now() - t0 < 5000) {
      btn = findSubmit();
      if (btn && !btn.disabled && btn.getAttribute("aria-disabled") !== "true")
        break;
      await sleep(100);
    }
    if (!btn) throw new Error("Send button not found");
    if (btn.disabled)
      throw new Error(
        "Send button still disabled after 5s — rate-limited or invalid address",
      );
    btn.click();
  };

  // 'success' | 'error' | 'timeout'
  const waitForOutcome = async () => {
    const t0 = Date.now();
    while (Date.now() - t0 < PER_WALLET_TIMEOUT) {
      if (findByText("button span", "Get more tokens")) return "success";
      const err = document.querySelector(
        '[role="alert"], .error, [data-testid*="error" i]',
      );
      if (err && err.offsetParent) return "error";
      await sleep(250);
    }
    return "timeout";
  };

  for (let i = 0; i < WALLETS.length; i++) {
    const w = WALLETS[i];
    console.log(`\n[${i + 1}/${WALLETS.length}] ${w}`);
    try {
      await ensureNetwork();
      await fillWallet(w);
      await clickSubmit();
    } catch (e) {
      console.error("  step failed:", e.message);
      console.warn(`  resume by trimming WALLETS to start at index ${i}`);
      break;
    }

    const outcome = await waitForOutcome();
    console.log(`  → ${outcome}`);
    if (outcome !== "success") {
      console.warn(
        `  stopping. Resume by trimming WALLETS to start at index ${i}`,
      );
      break;
    }

    findByText("button span", "Get more tokens").closest("button").click();
    await sleep(800); // form re-mount
  }

  console.log("\ndone.");
})();
