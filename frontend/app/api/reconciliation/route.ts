import { NextResponse } from "next/server";

const apiUrl = process.env.LEDGERLENS_API_URL ?? "http://localhost:8010";

export async function POST() {
  const batchResponse = await fetch(`${apiUrl}/api/v1/demo-batch`, { cache: "no-store" });
  if (!batchResponse.ok) return NextResponse.json({ detail: "The reconciliation API is unavailable." }, { status: 503 });
  const batch = await batchResponse.json();
  const result = await fetch(`${apiUrl}/api/v1/reconciliations`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ records: batch.records, ground_truth_links: batch.ground_truth_links }), cache: "no-store" });
  return NextResponse.json(await result.json(), { status: result.status });
}
