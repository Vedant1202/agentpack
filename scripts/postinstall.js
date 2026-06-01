#!/usr/bin/env node

const https = require("https");
const fs = require("fs");
const path = require("path");

const pkg = require("../package.json");
const version = pkg.version;
const repo = "Vedant1202/agentpack";

const PLATFORM_MAP = {
  darwin: "agentpack",
  linux: "agentpack",
};

const platform = process.platform;
const assetName = PLATFORM_MAP[platform];

if (!assetName) {
  console.error(
    `[agentpack] Unsupported platform: ${platform}. Pre-built binaries are only available for macOS and Linux.`
  );
  process.exit(1);
}

const url = `https://github.com/${repo}/releases/download/v${version}/${assetName}`;
const destDir = path.join(__dirname, "..", "dist");
const dest = path.join(destDir, "agentpack");

if (fs.existsSync(dest)) {
  process.exit(0);
}

if (!fs.existsSync(destDir)) {
  fs.mkdirSync(destDir, { recursive: true });
}

console.log(`[agentpack] Downloading binary from ${url} ...`);

function download(url, dest, cb) {
  https
    .get(url, (res) => {
      if (res.statusCode === 301 || res.statusCode === 302) {
        return download(res.headers.location, dest, cb);
      }
      if (res.statusCode !== 200) {
        return cb(new Error(`HTTP ${res.statusCode} for ${url}`));
      }
      const file = fs.createWriteStream(dest);
      res.pipe(file);
      file.on("finish", () => file.close(cb));
      file.on("error", (err) => {
        fs.unlink(dest, () => {});
        cb(err);
      });
    })
    .on("error", cb);
}

download(url, dest, (err) => {
  if (err) {
    console.error(`[agentpack] Download failed: ${err.message}`);
    process.exit(1);
  }
  fs.chmodSync(dest, 0o755);
  console.log(`[agentpack] Binary installed to ${dest}`);
});
