#!/usr/bin/env node

const { execFileSync } = require("child_process");
const path = require("path");

const binary = path.join(__dirname, "..", "dist", "agentpack");

try {
  execFileSync(binary, process.argv.slice(2), { stdio: "inherit" });
} catch (err) {
  process.exit(err.status ?? 1);
}
