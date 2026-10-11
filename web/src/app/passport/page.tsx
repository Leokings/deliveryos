"use client";

import { useCallback, useEffect, useState } from "react";
import { ADDRESS_PATTERN } from "@/lib/protocol";

type Receipt = {
  receipt_id: string;
  job_id: string;
  version: number;
  verdict: string;
  criterion_statuses: string[];
  evidence_fingerprint: string;
  decided_epoch: number;
  finality: string;
  source_contract: string;
};
type Passport = {
  chain_id: number;
  profile: {
    wallet: string;
    display_name: string;
    bio: string;
    capabilities: string[];
    profile_claims: string;
  };
  receipt_count: number;
  receipts: Receipt[];
  receipts_returned: number;
};

function shorten(value: string) {
  return value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value;
}

function date(epoch: number) {
  return epoch > 0
    ? new Date(epoch * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }) + " UTC"
    : "Time unavailable";
}

export default function ProviderPassportPage() {
  const [wallet, setWallet] = useState("");
  const [passport, setPassport] = useState<Passport | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const lookup = useCallback(async (address: string) => {
    setError("");
    setPassport(null);
    if (!ADDRESS_PATTERN.test(address)) {
      setError("Enter a valid 0x-prefixed wallet address.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`/api/passport?wallet=${encodeURIComponent(address)}`, { cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? `Passport lookup failed (${response.status}).`);
      setPassport(body as Passport);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Passport lookup failed.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    const address = new URLSearchParams(window.location.search).get("wallet");
    if (address && ADDRESS_PATTERN.test(address)) {
      setWallet(address);
      void lookup(address);
    }
  }, [lookup]);

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const address = wallet.trim();
    const url = new URL(window.location.href);
    url.searchParams.set("wallet", address);
    window.history.replaceState(null, "", url);
    void lookup(address);
  }

  return <main className="passport-page">
    <header className="passport-nav">
      <a href="/" className="brand"><span className="brand-mark">d<span>•</span></span><span>delivery<span className="brand-accent">os</span></span></a>
      <a href="/" className="passport-back">Back to work exchange <span aria-hidden="true">↗</span></a>
    </header>
    <section className="passport-hero">
      <div className="passport-eyebrow"><span className="live-pulse" /> PUBLIC PROVIDER PASSPORT</div>
      <h1>A record of work.<br /><em>Not a trust score.</em></h1>
      <p>Look up a Studionet wallet to see its published profile and finalized GenLayer consensus outcomes from DeliveryOS V5 and V6.</p>
      <form className="passport-lookup" onSubmit={submit}>
        <label htmlFor="passport-wallet">Provider wallet address</label>
        <div className="passport-input-row">
          <input id="passport-wallet" value={wallet} onChange={(event) => setWallet(event.target.value)} placeholder="0x…" autoComplete="off" spellCheck={false} />
          <button type="submit" disabled={busy}>{busy ? "Looking…" : "Look up"}<span aria-hidden="true">→</span></button>
        </div>
      </form>
      <div className="passport-boundary"><strong>Read this fairly.</strong> Capability tags and bios are self-reported. Outcome receipts record only validator decisions; they are not endorsements, a quality score, or proof that every real-world claim is true. V6 adds recovery for failed receipt callbacks.</div>
    </section>

    {error && <div className="passport-alert" role="status">{error}</div>}
    {passport && <section className="passport-results" aria-live="polite">
      <article className="passport-profile">
        <div className="passport-profile-top"><div><div className="passport-eyebrow">PROVIDER PROFILE</div><h2>{passport.profile.display_name || "No name published"}</h2></div><span className="passport-count">{passport.receipt_count} {passport.receipt_count === 1 ? "outcome" : "outcomes"}</span></div>
        <code className="passport-address">{passport.profile.wallet}</code>
        <p>{passport.profile.bio || "This wallet has not published a profile bio."}</p>
        <div className="passport-tags">{passport.profile.capabilities.length ? passport.profile.capabilities.map((tag) => <span key={tag}>{tag}</span>) : <small>No capability tags published</small>}</div>
        <small className="passport-self-report">Profile claims: {passport.profile.profile_claims.replaceAll("_", " ").toLowerCase()}</small>
      </article>

      <div className="passport-receipts-heading"><div><div className="passport-eyebrow">FINALIZED CONSENSUS RECORD</div><h2>Work outcomes</h2></div><span>{passport.receipts_returned} recent records shown</span></div>
      {passport.receipts.length === 0 ? <div className="passport-empty">No consensus outcome receipts are recorded for this wallet yet.</div> : <div className="passport-receipts">{passport.receipts.map((receipt, index) => <article className="passport-receipt" key={receipt.receipt_id || index}>
        <div className="passport-receipt-top"><span className={`passport-verdict verdict-${receipt.verdict.toLowerCase()}`}>{receipt.verdict}</span><time>{date(receipt.decided_epoch)}</time></div>
        <h3>{receipt.job_id} <small>· version {receipt.version}</small></h3>
        <p>GenLayer validator decision · {receipt.finality.replaceAll("_", " ").toLowerCase()}</p>
        <div className="passport-criteria">{receipt.criterion_statuses.map((status, criterion) => <span key={criterion}>Criterion {criterion + 1}: {status.replaceAll("_", " ").toLowerCase()}</span>)}</div>
        <div className="passport-fingerprint"><span>Evidence fingerprint</span><code title={receipt.evidence_fingerprint}>{shorten(receipt.evidence_fingerprint)}</code></div>
        <div className="passport-fingerprint"><span>Receipt ID</span><code title={receipt.receipt_id}>{shorten(receipt.receipt_id)}</code></div>
        <div className="passport-fingerprint"><span>Source contract</span><code title={receipt.source_contract}>{shorten(receipt.source_contract)}</code></div>
      </article>)}</div>}
      <p className="passport-pagination-note">Recent recorded entries from both registries, ordered by decision time. A recovered older decision can be recorded later. Agents can page through each registry’s complete history with MCP.</p>
    </section>}

    <section className="passport-agents">
      <div><div className="passport-eyebrow">AGENT ACCESS</div><h2>Use it from an agent, too.</h2><p>The public HTTP lookup needs no API key. For direct tool access, configure the DeliveryOS MCP server with <code>DELIVERYOS_PASSPORT_ADDRESS</code>.</p></div>
      <div className="passport-tool-list"><code>deliveryos_get_provider_profile</code><code>deliveryos_get_provider_receipt_count</code><code>deliveryos_get_provider_receipt</code><code>deliveryos_get_receipt_by_id</code><code>deliveryos_set_my_provider_profile</code><code>deliveryos_passport_receipt_status</code><code>deliveryos_sync_passport_receipt</code><small>Profile updates and V6 receipt recovery are signed by the agent’s own configured wallet. Reads never sign transactions.</small></div>
    </section>
    <footer className="passport-footer">Studionet · Chain {passport?.chain_id ?? 61999} · V5 history preserved · V6 receipt recovery through MCP · No payments.</footer>
  </main>;
}
