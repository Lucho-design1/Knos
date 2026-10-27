// The /check/ sample's recorded answer (web/check_sample.json, shipped with the site): knos-e2e #266, which Knos paid,
// and #265, which it refused, each read from GitHub as the page reads any pull request (web/check.js readPr) with Knos's
// own comment on it and the devnet transaction it names. The page shows this recording at once, labelled with its date,
// and reads the transaction's log line from devnet itself; it reads GitHub only for a pasted pull request.
//   node scripts/check_sample_record.mjs            write web/check_sample.json
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { SAMPLE, readPr, knosSaid } from "../web/check.js";

const out = { v: 1, about: "two pull requests of drexthealpha/knos-e2e as GitHub showed them, and Knos's comment on each; the devnet log line is read live",
  recorded: new Date().toISOString().replace(/\.\d+Z$/, "Z"), prs: {} };
for (const ref of SAMPLE) {
  const [r, said] = await Promise.all([readPr(ref), knosSaid(ref, { log: false })]);
  out.prs[String(ref.number)] = { ...r, said: said ? { line: said.line, sig: said.sig } : null };
  console.log(`#${ref.number}: ${r.cls}, "${r.line}"; Knos: ${said ? said.line.slice(0, 80) : "no comment"}; tx ${said && said.sig ? said.sig.slice(0, 8) : "none"}`);
}
writeFileSync(fileURLToPath(new URL("../web/check_sample.json", import.meta.url)), JSON.stringify(out, null, 1) + "\n");
