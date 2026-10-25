import { createHmac } from "node:crypto";

// Minimal RFC 6238 TOTP (SHA-1, 6 digits, 30s step) — no external deps.
const B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32Decode(s: string): Buffer {
  let bits = 0, value = 0;
  const out: number[] = [];
  for (const c of s.toUpperCase().replace(/=+$/, "")) {
    const i = B32.indexOf(c);
    if (i < 0) continue;
    value = (value << 5) | i;
    bits += 5;
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(out);
}

export function totp(secret: string, timeStep = 30, t = Date.now()): string {
  const counter = Math.floor(t / 1000 / timeStep);
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(counter));
  const h = createHmac("sha1", base32Decode(secret)).update(msg).digest();
  const off = h[h.length - 1] & 0xf;
  const code = ((h[off] & 0x7f) << 24 | h[off + 1] << 16 | h[off + 2] << 8 | h[off + 3]) % 1e6;
  return String(code).padStart(6, "0");
}
