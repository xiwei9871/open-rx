/* Deterministic UAT file fixtures — generated in code, never committed as
 * binary files (CI forbids tracked .stl/.dcm). Every fixture exposes its
 * bytes and sha256 so docs can reference stable identities. */
import { createHash } from "node:crypto";

function stl(name: string, seed: number, facets = 4): string {
  // Deterministic ASCII STL: `facets` triangles on a jittered grid.
  let s = `solid ${name}\n`;
  for (let i = 0; i < facets; i++) {
    const x = ((seed + i) % 7) * 0.5, y = ((seed + i * 3) % 5) * 0.4;
    s += `facet normal 0 0 1\n  outer loop\n`
      + `    vertex ${x} ${y} 0\n`
      + `    vertex ${x + 1} ${y} 0\n`
      + `    vertex ${x} ${y + 1} ${(seed % 3) * 0.2}\n`
      + `  endloop\nendfacet\n`;
  }
  return s + `endsolid ${name}\n`;
}

function fixture(name: string, body: string | Buffer) {
  const buf = Buffer.isBuffer(body) ? body : Buffer.from(body, "utf-8");
  const sha256 = createHash("sha256").update(buf).digest("hex");
  return { name, buffer: buf, bytes: buf.length, sha256 };
}

/* A structurally valid but semantically truncated STL — the final facet
 * block is cut mid-loop and end solid marker is absent. */
const BROKEN = `solid broken
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 0`;

// Minimal JPEG: SOI + JFIF header + EOI (decodable header, 1x1 gray).
const JPEG_1PX = Buffer.from([
  0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01,
  0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xff, 0xd9,
]);

// Minimal single-page PDF with visible text.
const PDF_MIN = `%PDF-1.1
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 100]/Contents 4 0 R
/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 58>>stream
BT /F1 12 Tf 20 50 Td (Lab instructions - UAT) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R>>
`;

/** One-off fixture with a run-unique seed — for tests that must NOT hit
 * the sha256 dedup path (e.g. interrupted uploads on re-runs). */
export function uniqueStl(tag: string, facets = 4) {
  const seed = (Date.now() + Math.floor(Math.random() * 1e6)) % 1e9;
  return fixture(`${tag}-${seed}.stl`, stl(tag, seed, facets));
}

const UPPER_BASIC = stl("upper-basic", 3);
const LOWER_BASIC = stl("lower-basic", 11);
const UPPER_EXPAND = stl("upper-expand", 23, 8);
const LOWER_EXPAND = stl("lower-expand", 31, 8);
const LARGE = stl("large-arch", 7, 400); // ~100 KB — enough to time preview

export const FIX = {
  upperBasic: fixture("upper-basic.stl", UPPER_BASIC),
  lowerBasic: fixture("lower-basic.stl", LOWER_BASIC),
  upperExpand: fixture("upper-expand.stl", UPPER_EXPAND),
  lowerExpand: fixture("lower-expand.stl", LOWER_EXPAND),
  /** Same bytes as upper-basic under a different name — dedup/attach path. */
  upperBasicAlias: fixture("upper-scan-copy.stl", UPPER_BASIC),
  broken: fixture("broken.stl", BROKEN),
  large: fixture("large-arch.stl", LARGE),
  photo: fixture("photo-intraoral.jpg", JPEG_1PX),
  notes: fixture("instructions.txt",
    "Seat expander with 0.25mm turns 2x/day. UAT synthetic note.\n"),
  notesPdf: fixture("notes.pdf", PDF_MIN),
} as const;

export function pwFile(f: (typeof FIX)[keyof typeof FIX]) {
  // setInputFiles payload for Playwright
  return {
    name: f.name,
    mimeType: f.name.endsWith(".stl") ? "model/stl"
      : f.name.endsWith(".jpg") ? "image/jpeg"
      : f.name.endsWith(".pdf") ? "application/pdf" : "text/plain",
    buffer: f.buffer,
  };
}
