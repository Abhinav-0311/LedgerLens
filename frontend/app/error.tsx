"use client";
export default function Error({ reset }: { reset: () => void }) { return <main className="workbench loading-shell"><p className="eyebrow">LedgerLens</p><h1>The workspace could not load.</h1><button className="primary-action" onClick={reset}>Try again</button></main>; }
