"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";
import {
  ADDRESS_PATTERN, CHAIN_ID, EXPLORER, JOB_ID_PATTERN,
  TX_HASH_PATTERN, contractFor, explainNextStep, explainStatus, repositoryPrefixFromInput, validateEvidenceUrl,
  type ContractVersion, type Job, type Submission,
} from "@/lib/protocol";

type Provider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  on?: (event: string, listener: (...args: unknown[]) => void) => void;
  removeListener?: (event: string, listener: (...args: unknown[]) => void) => void;
};
type WalletChoice = { id: string; name: string; provider: Provider };
type ConnectedWallet = WalletChoice & { address: string };
type Tab = "explore" | "create" | "manage" | "agents";
type TxStatus = { transaction_hash: string; status: string; consensus_result: string; execution_result: string; finalized_success: boolean };
type RecentJobs = { total: number; jobs: Job[] };
type Evidence = { url: string; sha256: string; size_bytes: number };

const EXAMPLE_JOBS: Record<ContractVersion, string> = {
  v1: "deliveryos_cb5bcede778b4248",
  v2: "package_f2131d0cd28244b2",
};
const EXAMPLE_REVIEW_TRANSACTIONS: Record<ContractVersion, string> = {
  v1: "0x058b7551a29bb6595ef9767cf2ff5050d129e71bc42e57429cb565e25e592424",
  v2: "0x650a6bd7014401f7ac35dfadfa55a8eb1856c327bced72b792a98ab954bc6ab7",
};
const PACKAGE_EXAMPLE = "https://raw.githubusercontent.com/Leokings/deliveryos/d8a674033c477f0d2bcae59ab8049cb2bdd86e37/examples/package_v2/package.json";

async function apiJson<T>(path: string, cache: RequestCache = "no-store"): Promise<T> {
  const response = await fetch(path, { cache });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error ?? `Request failed (HTTP ${response.status}).`);
  return body as T;
}

function short(value: string, left = 7, right = 5) {
  return value.length > left + right + 3 ? `${value.slice(0, left)}…${value.slice(-right)}` : value;
}

function utc(epoch: number) {
  return epoch ? `${new Date(epoch * 1000).toISOString().slice(0, 16).replace("T", " ")} UTC` : "—";
}

function statusTone(status: string) {
  if (status === "ACCEPTED") return "accepted";
  if (status === "REJECTED" || status === "EXPIRED" || status === "DECLINED") return "rejected";
  if (status === "REVISION" || status === "INCONCLUSIVE") return "review";
  return "pending";
}

export default function HomePage() {
  const [tab, setTab] = useState<Tab>("create");
  const [version, setVersion] = useState<ContractVersion>("v2");
  const [wallets, setWallets] = useState<WalletChoice[]>([]);
  const [wallet, setWallet] = useState<ConnectedWallet | null>(null);
  const [walletPicker, setWalletPicker] = useState(false);
  const [lookupId, setLookupId] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [recent, setRecent] = useState<RecentJobs | null>(null);
  const [recentError, setRecentError] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [txHash, setTxHash] = useState("");
  const [txStatus, setTxStatus] = useState<TxStatus | null>(null);
  const [jobId, setJobId] = useState("");
  const [provider, setProvider] = useState("");
  const [brief, setBrief] = useState("");
  const [criteriaText, setCriteriaText] = useState("");
  const [evidencePrefix, setEvidencePrefix] = useState("");
  const [dueLocal, setDueLocal] = useState("");
  const [maxRevisions, setMaxRevisions] = useState(1);
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const apiBase = version === "v2" ? "/api/v2" : "/api";
  const exampleJob = EXAMPLE_JOBS[version];

  useEffect(() => {
    setJobId((current) => current || `job_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`);
    setDueLocal((current) => {
      if (current) return current;
      const nextWeek = new Date(Date.now() + 7 * 86400_000);
      return new Date(nextWeek.getTime() - nextWeek.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    });
  }, []);

  function chooseVersion(next: ContractVersion) {
    if (next === version) return;
    setVersion(next);
    setJob(null); setSubmission(null); setRecent(null); setRecentError(""); setLookupId("");
    setError(""); setNotice(""); setTxHash(""); setTxStatus(null); setEvidenceUrl("");
    window.history.replaceState(null, "", `?version=${next}`);
  }

  const refreshRecent = useCallback(async () => {
    try {
      setRecentError("");
      setRecent(await apiJson<RecentJobs>(`${apiBase}/jobs?limit=3`, "default"));
    } catch (cause) {
      setRecentError((cause as Error).message);
    }
  }, [apiBase]);

  const loadJob = useCallback(async (id: string) => {
    setError("");
    if (!JOB_ID_PATTERN.test(id)) {
      setError("Use a job ID of 8–64 letters, numbers, underscores or hyphens.");
      return;
    }
    try {
      const nextJob = await apiJson<Job>(`${apiBase}/jobs/${encodeURIComponent(id)}`);
      const nextSubmission = nextJob.current_version
        ? await apiJson<Submission>(`${apiBase}/jobs/${encodeURIComponent(id)}/submissions/${nextJob.current_version}`)
        : null;
      setLookupId(id);
      setJob(nextJob);
      setSubmission(nextSubmission);
      window.history.replaceState(null, "", `?version=${version}&job=${encodeURIComponent(id)}`);
    } catch (cause) {
      setError((cause as Error).message);
    }
  }, [apiBase, version]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    // Older v1 invite links had no version parameter. Preserve those links.
    const requested = params.get("version") === "v1" || (!params.has("version") && params.has("job")) ? "v1" : "v2";
    if (requested !== version) {
      setVersion(requested);
      return;
    }
    const fromUrl = params.get("job");
    if (fromUrl && JOB_ID_PATTERN.test(fromUrl)) {
      setTab("manage");
      void loadJob(fromUrl).then(() => {
        document.getElementById("workspace")?.scrollIntoView({ block: "start" });
      });
    }
  }, [loadJob, version]);

  // Recent jobs are a convenience, not a reason to spend RPC calls on every
  // landing-page view. Load them only when someone opens Explore.
  useEffect(() => {
    if (tab === "explore" && !recent) refreshRecent();
  }, [tab, recent, refreshRecent]);

  function openTab(next: Tab) {
    selectTab(next);
    document.getElementById("workspace")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function selectTab(next: Tab) {
    setTab(next);
    setError("");
    setNotice("");
  }

  async function copyInviteLink() {
    if (!job) return;
    const link = `${window.location.origin}/?version=${version}&job=${encodeURIComponent(job.job_id)}`;
    try {
      await navigator.clipboard.writeText(link);
      setNotice(job.status === "PROPOSED" ? "Invite link copied. Send it to the named provider; they must connect that wallet to accept." : "Job link copied. Anyone can read this public job.");
    } catch {
      setError(`Could not access the clipboard. Copy this link manually: ${link}`);
    }
  }

  useEffect(() => {
    const found = new Map<string, WalletChoice>();
    const register = (choice: WalletChoice) => {
      if (!choice.provider?.request) return;
      for (const [id, existing] of found) {
        if (existing.provider === choice.provider) found.delete(id);
      }
      found.set(choice.id, choice);
      setWallets([...found.values()]);
    };
    const onAnnounce = (event: Event) => {
      const detail = (event as CustomEvent<{ info?: { uuid?: string; name?: string }; provider?: Provider }>).detail;
      if (detail?.provider) register({
        id: detail.info?.uuid ?? `injected-${found.size}`,
        name: detail.info?.name ?? "Browser wallet",
        provider: detail.provider,
      });
    };
    window.addEventListener("eip6963:announceProvider", onAnnounce);
    window.dispatchEvent(new Event("eip6963:requestProvider"));
    const injected = (window as Window & { ethereum?: Provider & { providers?: Provider[] } }).ethereum;
    if (injected?.providers?.length) injected.providers.forEach((item, i) => register({ id: `fallback-${i}`, name: `Wallet ${i + 1}`, provider: item }));
    else if (injected) register({ id: "injected", name: "Browser wallet", provider: injected });
    return () => window.removeEventListener("eip6963:announceProvider", onAnnounce);
  }, []);

  useEffect(() => {
    if (!wallet?.provider.on) return;
    const changed = () => { setWallet(null); setNotice("Wallet account or network changed. Connect again before signing."); };
    wallet.provider.on("accountsChanged", changed);
    wallet.provider.on("chainChanged", changed);
    return () => {
      wallet.provider.removeListener?.("accountsChanged", changed);
      wallet.provider.removeListener?.("chainChanged", changed);
    };
  }, [wallet]);

  async function ensureStudionet(providerInstance: Provider) {
    const wanted = `0x${CHAIN_ID.toString(16)}`;
    const current = await providerInstance.request({ method: "eth_chainId" });
    if (String(current).toLowerCase() !== wanted) {
      try {
        await providerInstance.request({ method: "wallet_switchEthereumChain", params: [{ chainId: wanted }] });
      } catch (cause) {
        const code = (cause as { code?: number }).code;
        if (code !== 4902) throw cause;
        await providerInstance.request({ method: "wallet_addEthereumChain", params: [{
          chainId: wanted, chainName: "GenLayer Studionet", rpcUrls: ["https://studio.genlayer.com/api"],
          nativeCurrency: { name: "GEN", symbol: "GEN", decimals: 18 },
          blockExplorerUrls: [EXPLORER],
        }] });
        await providerInstance.request({ method: "wallet_switchEthereumChain", params: [{ chainId: wanted }] });
      }
    }
    const confirmed = await providerInstance.request({ method: "eth_chainId" });
    if (String(confirmed).toLowerCase() !== wanted) throw new Error("Wallet is not on GenLayer Studionet (chain 61999).");
  }

  async function connectWallet(choice: WalletChoice) {
    setError(""); setNotice("");
    try {
      const accounts = await choice.provider.request({ method: "eth_requestAccounts" }) as string[];
      if (!Array.isArray(accounts) || !ADDRESS_PATTERN.test(accounts[0] ?? "")) throw new Error("Wallet did not provide a valid address.");
      await ensureStudionet(choice.provider);
      setWallet({ ...choice, address: accounts[0] });
      setWalletPicker(false);
      setNotice(`Connected ${choice.name} on Studionet. You will approve every write in your wallet.`);
    } catch (cause) {
      setError((cause as Error).message || "Wallet connection was cancelled.");
    }
  }

  function openWallet() {
    if (wallets.length === 1) connectWallet(wallets[0]);
    else if (wallets.length) setWalletPicker(true);
    else setError("No EIP-1193 wallet was detected. Install an EVM wallet extension or open this site in a wallet browser, then refresh.");
  }

  async function refreshTransaction() {
    if (!TX_HASH_PATTERN.test(txHash)) {
      setError("Enter a 0x-prefixed 32-byte transaction hash.");
      return;
    }
    try {
      const current = await apiJson<TxStatus>(`/api/transactions/${txHash}`);
      setTxStatus(current);
      if (current.status === "FINALIZED") {
        setNotice(current.finalized_success ? "Transaction finalized and executed successfully." : "Transaction finalized but did not execute successfully. No state change should be assumed.");
        if (job) await loadJob(job.job_id);
        await refreshRecent();
      }
    } catch (cause) {
      setError((cause as Error).message);
    }
  }

  async function write(method: string, args: Array<string | number>, nextJobId?: string) {
    if (!wallet) { openWallet(); return; }
    setError(""); setNotice(""); setBusy(true); setTxStatus(null);
    let submitted = "";
    try {
      await ensureStudionet(wallet.provider);
      type SDKProvider = NonNullable<NonNullable<Parameters<typeof createClient>[0]>["provider"]>;
      const client = createClient({ chain: studionet, account: wallet.address as `0x${string}`, provider: wallet.provider as SDKProvider });
      const hash = await client.writeContract({ address: contractFor(version), functionName: method, args, value: 0n });
      if (typeof hash !== "string" || !TX_HASH_PATTERN.test(hash)) throw new Error("The wallet did not return a GenLayer transaction hash. Check its activity before retrying.");
      submitted = hash;
      setTxHash(hash);
      setNotice("Transaction submitted. Waiting for consensus and execution; do not submit it again while its result is unknown.");
      for (let attempt = 0; attempt < 45; attempt++) {
        await new Promise((resolve) => window.setTimeout(resolve, 4000));
        try {
          const current = await apiJson<TxStatus>(`/api/transactions/${hash}`);
          setTxStatus(current);
          if (current.status === "FINALIZED") {
            if (!current.finalized_success) throw new Error(`Transaction finalized without successful execution (${current.consensus_result} / ${current.execution_result}).`);
            setNotice("Transaction finalized and executed. The job below is read from finalized chain state.");
            await loadJob(nextJobId ?? job?.job_id ?? "");
            await refreshRecent();
            return;
          }
        } catch (cause) {
          if ((cause as Error).message.startsWith("Transaction finalized without")) throw cause;
          // A newly submitted transaction may not be queryable for a few seconds.
        }
      }
      setNotice("Still pending. Save the transaction hash and use Check status; do not submit the same action again.");
    } catch (cause) {
      setError((cause as Error).message || "The wallet rejected the transaction.");
      if (submitted) setNotice("A transaction hash was returned. Check its status before any retry.");
    } finally {
      setBusy(false);
    }
  }

  async function createJob() {
    const criteria = criteriaText.split("\n").map((line) => line.trim()).filter(Boolean);
    const dueEpoch = Math.floor(new Date(dueLocal).getTime() / 1000);
    try {
      if (!JOB_ID_PATTERN.test(jobId)) throw new Error("Job ID must be 8–64 letters, digits, underscores or hyphens.");
      if (!ADDRESS_PATTERN.test(provider) || /^0x0{40}$/i.test(provider)) throw new Error("Enter a nonzero provider wallet address.");
      if (wallet && provider.toLowerCase() === wallet.address.toLowerCase()) throw new Error("Buyer and provider must be different wallets.");
      if (brief.trim().length < 20 || brief.trim().length > 1200) throw new Error("Brief must be 20–1,200 characters.");
      if (criteria.length < 1 || criteria.length > 4 || criteria.some((item) => item.length < 10 || item.length > 300) || new Set(criteria).size !== criteria.length) throw new Error("Use 1–4 distinct criteria, each 10–300 characters.");
      const normalizedPrefix = repositoryPrefixFromInput(evidencePrefix);
      if (!Number.isFinite(dueEpoch) || dueEpoch <= Date.now() / 1000 || dueEpoch > Date.now() / 1000 + 90 * 86400) throw new Error("Due date must be in the future and within 90 days.");
      if (![0, 1, 2].includes(maxRevisions)) throw new Error("Choose 0–2 revisions.");
      await write("create_job", [jobId, provider, brief.trim(), JSON.stringify(criteria), normalizedPrefix, dueEpoch, maxRevisions], jobId);
    } catch (cause) {
      setError((cause as Error).message);
    }
  }

  async function submitDelivery() {
    if (!job) return;
    try {
      validateEvidenceUrl(evidenceUrl);
      if (!evidenceUrl.startsWith(job.evidence_prefix)) throw new Error("Evidence is outside the repository prefix agreed by the buyer.");
      setNotice(version === "v2" ? "Checking the manifest and every pinned file before your wallet signs…" : "Checking the exact public bytes and SHA-256 before asking your wallet to sign…");
      const evidence = version === "v2"
        ? await apiJson<Evidence & { content_fingerprint: string }>(`/api/v2/packages/preflight?url=${encodeURIComponent(evidenceUrl)}&prefix=${encodeURIComponent(job.evidence_prefix)}&criteria=${job.criteria.length}`)
        : await apiJson<Evidence>(`/api/evidence?url=${encodeURIComponent(evidenceUrl)}`);
      if (version === "v2" && job.status === "REVISION" && submission?.content_fingerprint === (evidence as Evidence & { content_fingerprint: string }).content_fingerprint) {
        throw new Error("A revision must change at least one file, not just the manifest metadata.");
      }
      await write("submit_delivery", [job.job_id, evidence.url, evidence.sha256, evidence.size_bytes]);
    } catch (cause) {
      setError((cause as Error).message);
    }
  }

  const role = useMemo(() => wallet && job ? (wallet.address.toLowerCase() === job.buyer.toLowerCase() ? "buyer" : wallet.address.toLowerCase() === job.provider.toLowerCase() ? "provider" : "observer") : "observer", [wallet, job]);
  const canExpire = job && ["PROPOSED", "ACTIVE", "REVISION"].includes(job.status) && Date.now() / 1000 > job.submission_deadline_epoch;
  const canClose = job && submission && job.status === "SUBMITTED" && Date.now() / 1000 > Math.max(job.due_epoch, submission.submitted_epoch) + 7 * 86400;

  return <main>
    <div className="ambient ambient-one" aria-hidden="true" /><div className="ambient ambient-two" aria-hidden="true" />
    <header className="site-header wrap">
      <a className="brand" href="#top" aria-label="DeliveryOS home"><span className="brand-mark">d<span>•</span></span><span>delivery<span className="brand-accent">os</span></span></a>
      <nav className="desktop-nav" aria-label="Main navigation"><a href="#workspace" onClick={() => selectTab("create")}>Create request</a><a href="#workspace" onClick={() => selectTab("manage")}>Open invite</a><a href="#workspace" onClick={() => selectTab("agents")}>Agent setup</a></nav>
      <button className="wallet-button" onClick={openWallet} type="button"><span className="wallet-dot" />{wallet ? `${wallet.name} · ${short(wallet.address, 5, 4)}` : "Connect wallet"}</button>
    </header>

    <section className="hero wrap" id="top">
      <div className="hero-copy">
        <div className="eyebrow"><span className="live-pulse" /> LIVE ON GENLAYER STUDIONET</div>
        <h1>Work together.<br /><em>Know what&apos;s done.</em></h1>
        <p>Ask a person or AI agent to do a task. They accept, share the finished work, and you approve it—or ask GenLayer to review it.</p>
        <div className="hero-actions"><button className="button button-primary" onClick={() => openTab("create")}>Create a request <span>↗</span></button><button className="button button-light" onClick={() => openTab("manage")}>I have an invite <span>→</span></button></div>
        <button className="hero-example" onClick={() => { openTab("manage"); loadJob(exampleJob); }}>Explore a completed example · no wallet needed →</button>
        <p className="hero-note">Connect a wallet only when you need to approve an on-chain action. No payment happens here.</p>
      </div>
      <div className="handoff-card" aria-label="Human and agent handoff">
        <span className="mini-label">THREE STEPS TO A CLEAR RESULT</span>
        <div className="handoff-row"><span className="handoff-icon">1</span><div><strong>Make a request</strong><small>Describe the task and invite one person or agent by wallet address.</small></div></div>
        <div className="handoff-row"><span className="handoff-icon warm">2</span><div><strong>Share the work</strong><small>The invitee accepts and submits public files from GitHub.</small></div></div>
        <div className="handoff-row"><span className="handoff-icon mint">3</span><div><strong>Record a decision</strong><small>Approve the work yourself, or request GenLayer review.</small></div></div>
        <button className="handoff-agent" onClick={() => openTab("agents")}>Using an AI agent? See how it connects <span>→</span></button>
      </div>
    </section>

    <section className="workspace-section" id="workspace"><div className="wrap"><div className="workspace-intro"><div><span className="mini-label">YOUR WORKSPACE</span><h2>What would you like to do?</h2><p>You can look around without a wallet. Connect one only when you are ready to sign.</p></div><div className="network-chip"><span className="live-pulse" /> Studionet · 61999</div></div>
      <details className="format-details"><summary>Delivery format: {version === "v2" ? "up to 6 public files" : "one public file"} <span>Change format</span></summary><div className="protocol-picker" role="group" aria-label="Delivery protocol"><button type="button" className={version === "v1" ? "selected" : ""} aria-pressed={version === "v1"} onClick={() => chooseVersion("v1")}>Single file <span>v1</span></button><button type="button" className={version === "v2" ? "selected" : ""} aria-pressed={version === "v2"} onClick={() => chooseVersion("v2")}>Up to six files <span>v2</span></button><p>{version === "v2" ? "Recommended for multi-file work. The provider submits a GitHub package manifest." : "Legacy format for one small text file."}</p></div></details>
      <div className="workspace-shell"><div className="tabs" role="tablist" aria-label="Workspace sections">
        {([ ["create", "Create request"], ["manage", "Open invite"], ["explore", "Explore jobs"], ["agents", "Agent setup"] ] as [Tab, string][]).map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={tab === key} className={`tab ${tab === key ? "active" : ""}`} onClick={() => selectTab(key)}>{label}</button>)}
      </div>
      {(error || notice || txHash) && <div className="feedback-stack" aria-live="polite">{error && <div className="alert alert-error"><span>!</span><p>{error}</p><button onClick={() => setError("")} aria-label="Dismiss error">×</button></div>}{notice && <div className="alert alert-info"><span>i</span><p>{notice}</p><button onClick={() => setNotice("")} aria-label="Dismiss notice">×</button></div>}{txHash && <div className="tx-line"><span>Latest transaction</span><code>{short(txHash, 14, 10)}</code><button onClick={refreshTransaction}>Check status ↻</button>{txStatus && <strong className={txStatus.finalized_success ? "tx-good" : ""}>{txStatus.status} · {txStatus.execution_result}</strong>}</div>}</div>}

      {tab === "explore" && <div className="panel-grid"><div className="panel-main"><h3>Find a decision</h3><p className="muted">Every job is public on Studionet. Search by its exact ID or open a recent one.</p><form className="search-row" onSubmit={(event) => { event.preventDefault(); loadJob(lookupId.trim()); }}><label className="sr-only" htmlFor="lookup">Job ID</label><input id="lookup" value={lookupId} onChange={(event) => setLookupId(event.target.value)} placeholder="Enter a job ID" /><button className="button button-dark" type="submit">Look up <span>→</span></button></form><div className="recent-head"><h4>Recent jobs</h4><button className="text-button" onClick={refreshRecent}>Refresh ↻</button></div>{recentError && <p className="inline-error">{recentError}</p>}{recent?.jobs.length ? <div className="recent-list">{recent.jobs.map((item) => <button key={item.job_id} className="recent-item" onClick={() => loadJob(item.job_id)}><span><strong>{item.job_id}</strong><small>{item.brief}</small></span><span className={`status status-${statusTone(item.status)}`}>{item.status}</span><b>↗</b></button>)}</div> : <div className="empty-state">{recentError ? "Recent jobs are temporarily unavailable. You can still look up a known job ID." : recent ? "No jobs have been created yet." : "Loading finalized jobs…"}</div>}<p className="subtle">Showing the {recent?.jobs.length ?? 0} newest of {recent?.total ?? "—"} on-chain jobs.</p></div><aside className="panel-aside"><div className="aside-illustration"><span>↗</span><span>✓</span><span>↘</span></div><span className="mini-label">FIRST TIME HERE?</span><h3>Open a real example.</h3><p>See an accepted job whose validator-review transaction finalized on Studionet.</p><button className="text-button large" onClick={() => loadJob(exampleJob)}>View verified example <span>→</span></button></aside></div>}

      {tab === "create" && <div className="panel-grid">
        <div className="panel-main">
          <h3>Create a work request</h3>
          <p className="muted">Invite one specific person or agent. They will accept before they can deliver.</p>
          <div className="form-grid">
            <label className="field"><span>Reference ID</span><div className="inline-input"><input value={jobId} onChange={(event) => setJobId(event.target.value)} placeholder="A unique job reference" maxLength={64} /><button type="button" onClick={() => setJobId(`job_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`)}>New ID</button></div></label>
            <label className="field"><span>Invitee&apos;s wallet address</span><input value={provider} onChange={(event) => setProvider(event.target.value)} placeholder="0x…" /></label>
            <label className="field field-full"><span>What should they make?</span><textarea value={brief} onChange={(event) => setBrief(event.target.value)} rows={3} placeholder="Describe the finished result in plain language." /></label>
            <label className="field field-full"><span>What counts as complete? <small>one clear point per line, up to 4</small></span><textarea value={criteriaText} onChange={(event) => setCriteriaText(event.target.value)} rows={4} placeholder={"Includes a 200-word summary for new users.\nNames the three approved audience groups."} /></label>
            <label className="field field-full"><span>Public GitHub repository for the work</span><input value={evidencePrefix} onChange={(event) => setEvidencePrefix(event.target.value)} placeholder="https://github.com/owner/repository" /><small>Paste the normal repository link. We convert it to the exact public source URL required by the contract. Do not use private client material.</small></label>
            <label className="field"><span>Due date</span><input type="datetime-local" value={dueLocal} onChange={(event) => setDueLocal(event.target.value)} /></label>
            <label className="field"><span>Allowed revisions</span><select value={maxRevisions} onChange={(event) => setMaxRevisions(Number(event.target.value))}><option value={0}>No revisions</option><option value={1}>1 revision</option><option value={2}>2 revisions</option></select></label>
          </div>
          <div className="form-footer"><p>This request is public. Your wallet will ask you to approve it. No funds move.</p><button type="button" className="button button-primary" disabled={busy} onClick={createJob}>{busy ? "Waiting for confirmation…" : "Create request"} <span>↗</span></button></div>
        </div>
        <aside className="panel-aside guidance"><span className="mini-label">WHAT HAPPENS NEXT</span><h3>A link, not a job board.</h3><ol><li>Approve this request in your wallet.</li><li>Copy its link and send it to your invitee.</li><li>They connect the wallet you named and accept.</li></ol><div className="aside-note">Tip: describe something visible in the final files. GenLayer cannot confirm private or real-world claims from a document alone.</div></aside>
      </div>}

      {tab === "manage" && <div className="panel-grid"><div className="panel-main">
        <h3>Open an invitation</h3>
        <p className="muted">Use the link someone sent you, or paste the job reference below. You can read it before connecting a wallet.</p>
        <form className="search-row" onSubmit={(event) => { event.preventDefault(); loadJob(lookupId.trim()); }}><label className="sr-only" htmlFor="manage-lookup">Job reference</label><input id="manage-lookup" value={lookupId} onChange={(event) => setLookupId(event.target.value)} placeholder="Paste a job reference" /><button className="button button-dark" type="submit">Open job <span>→</span></button></form>
        {job ? <div className="actions-card"><div className="actions-title"><div><span className="mini-label">NEXT STEP</span><strong>{wallet ? role : "Read first"}</strong></div><span className={`status status-${statusTone(job.status)}`}>{job.status}</span></div>
          <p className="next-step-copy">{explainNextStep(job.status, role)}</p>
          {!wallet && !["ACCEPTED", "REJECTED", "INCONCLUSIVE", "EXPIRED", "CANCELLED", "DECLINED"].includes(job.status) && <button type="button" className="inline-connect" onClick={openWallet}>Connect the invited wallet →</button>}
          {wallet && role === "observer" && <p className="muted">This wallet is not the buyer or invitee. It can read the job, but cannot accept or approve it.</p>}
          <div className="action-buttons">
          {job.status === "PROPOSED" && role === "provider" && <><button disabled={busy} onClick={() => write("accept_job", [job.job_id])}>Accept request ↗</button><button disabled={busy} className="secondary-action" onClick={() => write("decline_job", [job.job_id])}>Decline</button></>}
          {job.status === "PROPOSED" && role === "buyer" && <button disabled={busy} className="secondary-action" onClick={() => write("cancel_proposal", [job.job_id])}>Cancel proposal</button>}
          {["ACTIVE", "REVISION"].includes(job.status) && role === "provider" && <div className="submit-box"><label className="field"><span>{version === "v2" ? "Link to your public package manifest" : "Link to your public finished file"}</span><input value={evidenceUrl} onChange={(event) => setEvidenceUrl(event.target.value)} placeholder={`${job.evidence_prefix}<40-character-commit>/${version === "v2" ? "package.json" : "file.txt"}`} /><small>Use a full GitHub commit link, not a branch link. We check the exact files before your wallet signs.</small></label>{version === "v2" && <a className="evidence-help" href="https://github.com/Leokings/deliveryos#evidence-packages-v2" target="_blank" rel="noreferrer">How to prepare a package ↗</a>}<button disabled={busy} onClick={submitDelivery}>Submit finished work ↗</button></div>}
          {job.status === "SUBMITTED" && role === "buyer" && <button disabled={busy} onClick={() => write("accept_delivery", [job.job_id])}>Approve finished work ↗</button>}
          {job.status === "SUBMITTED" && (role === "buyer" || role === "provider") && <button disabled={busy} className="outline-action" onClick={() => write("evaluate_delivery", [job.job_id])}>Ask GenLayer to review ↗</button>}
          {canExpire && <button disabled={busy} className="secondary-action" onClick={() => write("expire_undelivered", [job.job_id])}>Close overdue job</button>}
          {canClose && <button disabled={busy} className="secondary-action" onClick={() => write("close_unreviewed", [job.job_id])}>Close unreviewed submission</button>}
          </div></div> : <div className="empty-state">Open a shared link or enter a job reference to see what happens next.</div>}
        </div><aside className="panel-aside guidance"><span className="mini-label">WHY CONNECT A WALLET?</span><h3>Read freely. Sign your actions.</h3><p>Anyone can inspect a job. Only the named buyer and invitee can approve their own steps.</p><div className="aside-note">Never enter a private key on this site. After signing, wait for the transaction to finish before trying again.</div></aside></div>}

      {tab === "agents" && <div className="panel-grid"><div className="panel-main">
        <h3>Use it from your AI agent</h3>
        <p className="muted">DeliveryOS is a tool for an agent you already run. It is not an agent that works by itself.</p>
        <div className="agent-simple-flow"><div><b>1</b><span>Install the connector from the public GitHub repo.</span></div><div><b>2</b><span>Add the local MCP command to your agent host.</span></div><div><b>3</b><span>Give it a job ID. It can read, suggest a next step, and sign only with its authorized wallet.</span></div></div>
        <a className="button button-primary agent-guide" href="https://github.com/Leokings/deliveryos#let-an-ai-agent-use-it" target="_blank" rel="noreferrer">Open the agent setup guide <span>↗</span></a>
        <details className="agent-advanced"><summary>API endpoints and technical details</summary><div className="api-card"><span>READ A JOB</span><code>GET {apiBase}/jobs/{exampleJob}</code><a href={`${apiBase}/jobs/${exampleJob}`} target="_blank" rel="noreferrer">Open response ↗</a></div><div className="api-card"><span>CHECK A TRANSACTION</span><code>GET /api/transactions/{'{transaction_hash}'}</code><a href={version === "v2" ? "/api/v2/openapi" : "/api/openapi"} target="_blank" rel="noreferrer">API reference ↗</a></div><div className="api-card"><span>LOCAL MCP COMMAND</span><code>python -m deliveryos_agent.mcp_server</code></div>{version === "v2" && <div className="api-card"><span>EXAMPLE PACKAGE</span><a href={PACKAGE_EXAMPLE} target="_blank" rel="noreferrer">Open a real two-file manifest ↗</a></div>}<div className="api-disclaimer">Public reads need no API key. An API key alone cannot sign a GenLayer transaction; the buyer or provider wallet must sign.</div></details>
      </div><aside className="panel-aside guidance"><span className="mini-label">IMPORTANT BOUNDARY</span><h3>Local MCP, not a hosted bot.</h3><p>Your agent host runs the connector. Keep its signing key in that host&apos;s secret storage, never on this site or in a chat.</p><div className="aside-note">The agent should check that each transaction finalized and executed successfully, then read the updated job.</div></aside></div>}
      </div>
      {job && <div className="job-detail"><div className="job-head"><div><span className="mini-label">FINALIZED CHAIN STATE · {version.toUpperCase()}</span><h3>{job.job_id}</h3><p>{explainStatus(job.status)}</p></div><div className="job-head-actions"><span className={`status status-${statusTone(job.status)}`}>{job.status}</span><button onClick={() => loadJob(job.job_id)} className="text-button">Refresh ↻</button></div></div><div className="job-fields"><div><span>Buyer</span><code title={job.buyer}>{short(job.buyer, 9, 7)}</code></div><div><span>Provider</span><code title={job.provider}>{short(job.provider, 9, 7)}</code></div><div><span>Due</span><strong>{utc(job.due_epoch)}</strong></div><div><span>Current version</span><strong>{job.current_version || "Awaiting delivery"}</strong></div></div><div className="job-body"><div><span className="mini-label">THE BRIEF</span><p>{job.brief}</p></div><div><span className="mini-label">ACCEPTANCE CRITERIA</span><ol>{job.criteria.map((item, index) => <li key={index}><span className={`criterion-indicator ${job.latest_statuses[index]?.toLowerCase() ?? ""}`}>{job.latest_statuses[index] ?? String(index + 1).padStart(2, "0")}</span>{item}</li>)}</ol></div></div>{submission && <div className="submission-row"><div><span className="mini-label">VERSION {submission.version} EVIDENCE</span><a href={submission.url} target="_blank" rel="noreferrer">{short(submission.url, 48, 12)} ↗</a><small>SHA-256 {submission.sha256} · {submission.size_bytes} bytes{submission.evidence_type === "PACKAGE" ? ` · ${submission.file_count || "pending"} files · ${submission.total_bytes || "pending"} source bytes` : ""}</small></div><span className={`status status-${statusTone(submission.verdict || "SUBMITTED")}`}>{submission.verdict || "AWAITING REVIEW"}</span></div>}<div className="job-bottom"><span>Scope SHA-256 <code>{short(job.scope_digest, 15, 14)}</code></span><span>Decision source <strong>{job.decision_source || "Pending"}</strong></span><span>Deadline <strong>{utc(job.submission_deadline_epoch)}</strong></span></div></div>}
      {job?.job_id === exampleJob && <div className="proof-strip"><span className="proof-check" aria-hidden="true">✓</span><div><strong>This example happened on Studionet.</strong><p>Open its finalized review transaction and the recorded test steps.</p></div><a href={`/api/transactions/${EXAMPLE_REVIEW_TRANSACTIONS[version]}`} target="_blank" rel="noreferrer">Review transaction ↗</a><a href={`https://github.com/Leokings/deliveryos/blob/main/deployments/${version === "v2" ? "studionet_packages.json" : "studionet.json"}`} target="_blank" rel="noreferrer">Test record ↗</a></div>}
      {job && <div className="share-strip"><div><strong>{job.status === "PROPOSED" ? "Ready to hand this job over?" : "Keep everyone on the same page."}</strong><span>{job.status === "PROPOSED" ? "Send the link to the named provider. Only their wallet can accept." : "Share this public, version-specific job link with a person or agent."}</span></div><button type="button" onClick={copyInviteLink}>Copy job link ↗</button></div>}
    </div></section>

    <section className="limit-section wrap"><div className="limit-card"><span className="mini-label">KNOW THE LIMITS</span><h2>Clear evidence. Human judgment.</h2><p>DeliveryOS pins public bytes and records decisions; it cannot prove every real-world claim. Evidence is public, validator judgment can be wrong, and neither version moves funds.</p><a href="https://github.com/Leokings/deliveryos/blob/main/SECURITY.md" target="_blank" rel="noreferrer">Read the security model <span>↗</span></a></div></section>
    <footer className="footer" id="developers"><div className="wrap footer-inner"><div><a className="brand" href="#top"><span className="brand-mark">d<span>•</span></span><span>delivery<span className="brand-accent">os</span></span></a><p>Clear decisions for delivered work.</p></div><div className="footer-links"><a href={version === "v2" ? "/api/v2/openapi" : "/api/openapi"} target="_blank">API spec ↗</a><a href="https://github.com/Leokings/deliveryos" target="_blank" rel="noreferrer">GitHub ↗</a><a href={EXPLORER} target="_blank" rel="noreferrer">Studionet explorer ↗</a></div><small>GenLayer Studionet · Chain {CHAIN_ID} · Contract {short(contractFor(version), 10, 8)}<br />Decision protocol {version}. No escrow or payment processing.</small></div></footer>

    {walletPicker && <div className="modal-backdrop" role="presentation" onMouseDown={() => setWalletPicker(false)}><div className="wallet-modal" role="dialog" aria-modal="true" aria-labelledby="wallet-title" onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" onClick={() => setWalletPicker(false)} aria-label="Close wallet chooser">×</button><span className="mini-label">CHOOSE YOUR WALLET</span><h2 id="wallet-title">Connect to Studionet</h2><p>Pick the wallet that holds your buyer or provider address. You will approve every on-chain write.</p><div className="wallet-list">{wallets.map((choice) => <button key={choice.id} onClick={() => connectWallet(choice)}><span className="wallet-symbol">◈</span>{choice.name}<span>→</span></button>)}</div></div></div>}
  </main>;
}
