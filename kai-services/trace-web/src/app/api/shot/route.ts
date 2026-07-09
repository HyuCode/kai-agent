// 操作ごとの OBS スクショを配信する。shot_daemon が
// <HERMES_HOME>/kai_trace/shots/<session>/<n>.jpg に保存したものを返す。
import fs from "node:fs";
import path from "node:path";
import { traceDir } from "@/lib/trace";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET(req: Request) {
  const url = new URL(req.url);
  const session = url.searchParams.get("session") ?? "";
  const n = url.searchParams.get("n") ?? "";
  // パストラバーサル対策: session は英数字・ハイフン・アンダースコアのみ、n は数字のみ。
  // `.` `..` を明示的に拒否する（`[\w.-]` はドットを許すため。Issue #77 L1）
  if (!/^[\w-]{1,64}$/.test(session) || session === "." || session === ".." ||
      !/^\d{1,9}$/.test(n)) {
    return new Response("bad request", { status: 400 });
  }
  const file = path.join(traceDir(), "shots", session, `${n}.jpg`);
  try {
    const buf = fs.readFileSync(file);
    return new Response(buf, {
      headers: {
        "Content-Type": "image/jpeg",
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    });
  } catch {
    return new Response("not found", { status: 404 });
  }
}
