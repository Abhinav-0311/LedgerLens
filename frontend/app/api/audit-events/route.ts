import { NextResponse } from "next/server";
const apiUrl = process.env.LEDGERLENS_API_URL ?? "http://localhost:8010";
export async function GET() { const result = await fetch(`${apiUrl}/api/v1/audit-events`, { cache: "no-store" }); return NextResponse.json(await result.json(), { status: result.status }); }
