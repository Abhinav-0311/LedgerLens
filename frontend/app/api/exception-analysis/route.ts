import { NextRequest, NextResponse } from "next/server";
const apiUrl = process.env.LEDGERLENS_API_URL ?? "http://localhost:8010";
export async function POST(request: NextRequest) {
  const result = await fetch(`${apiUrl}/api/v1/exception-analyses`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(await request.json()), cache: "no-store" });
  return NextResponse.json(await result.json(), { status: result.status });
}
