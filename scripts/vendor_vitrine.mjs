// Build only reviewed Vitrine components. Maintainer operation; no production npm.
import { createRequire } from "node:module";
import { readFile, writeFile, mkdir, copyFile, rm } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
const revision = "07ab87825dfbe100b5a3357e4d42b8789f76ffad";
const source = resolve(process.argv[2] || "");
if (
  execFileSync("git", ["rev-parse", "HEAD"], {
    cwd: source,
    encoding: "utf8",
  }).trim() !== revision
)
  throw Error("Use the pinned reviewed Vitrine checkout");
if (
  execFileSync("git", ["status", "--porcelain", "--untracked-files=no"], {
    cwd: source,
    encoding: "utf8",
  }).trim()
)
  throw Error("Vitrine source must be clean");
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = resolve(root, "portal/static/portal/vendor/vitrine");
const require = createRequire(resolve(source, "package.json"));
const { build } = require("esbuild");
await mkdir(output, { recursive: true });
const entry = resolve(source, ".bearings-entry.js");
await writeFile(
  entry,
  `export {VtMap} from './src/components/map/vt-map.js';\nexport {VtStats} from './src/components/stats/vt-stats.js';\nexport {VtCode} from './src/components/code/vt-code.js';\nexport {VtChart} from './src/components/chart/vt-chart.js';\nexport {configure} from './src/entries/api.js';\n`,
);
const raw = {
  name: "raw-css",
  setup(b) {
    b.onResolve({ filter: /\.css\?raw$/ }, (args) => ({
      path: resolve(args.resolveDir, args.path.replace(/\?raw$/, "")),
      namespace: "raw-css",
    }));
    b.onLoad({ filter: /.*/, namespace: "raw-css" }, async (args) => ({
      contents: await readFile(args.path, "utf8"),
      loader: "text",
    }));
  },
};
const options = {
  bundle: true,
  minify: true,
  format: "esm",
  target: ["es2022"],
  legalComments: "eof",
  define: { __VITRINE_VERSION__: JSON.stringify("0.14.0") },
  banner: {
    js: "/*! Vitrine 0.14.0 | MIT | ecrou-exact/vitrine | See LICENSE and THIRD_PARTY_NOTICES.md */",
  },
};
try {
  await build({
    ...options,
    entryPoints: [entry],
    outfile: resolve(output, "vitrine.js"),
    plugins: [raw],
  });
  await build({
    ...options,
    entryPoints: [resolve(source, "src/vendor/geo.js")],
    outfile: resolve(output, "geo.js"),
  });
  await build({
    ...options,
    entryPoints: [resolve(source, "src/vendor/echarts.js")],
    outfile: resolve(output, "echarts.js"),
  });
} finally {
  await rm(entry);
}
for (const name of ["LICENSE", "THIRD_PARTY_NOTICES.md"])
  await copyFile(resolve(source, name), resolve(output, name));
const metadata = {
  repository: "https://github.com/ecrou-exact/vitrine",
  revision,
  version: "0.14.0",
  components: ["map", "stats", "code", "chart"],
  lock_sha256: createHash("sha256")
    .update(await readFile(resolve(source, "package-lock.json")))
    .digest("hex"),
};
await writeFile(
  resolve(output, "PROVENANCE.json"),
  JSON.stringify(metadata, null, 2) + "\n",
);
const files = [
  "vitrine.js",
  "geo.js",
  "echarts.js",
  "LICENSE",
  "THIRD_PARTY_NOTICES.md",
  "PROVENANCE.json",
];
await writeFile(
  resolve(output, "SHA256SUMS"),
  (
    await Promise.all(
      files.map(
        async (name) =>
          createHash("sha256")
            .update(await readFile(resolve(output, name)))
            .digest("hex") +
          "  " +
          name,
      ),
    )
  ).join("\n") + "\n",
);
console.log(
  "Built pinned map/stats/code/chart and local geographic/chart engines in " +
    output,
);
