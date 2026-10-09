import { createHash, randomUUID } from "node:crypto";
import {
  existsSync,
  lstatSync,
  linkSync,
  mkdirSync,
  readFileSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const manifestPath = path.join(
  repositoryRoot,
  "docs",
  "PRESENTATION_WORKSPACE",
  "corpus-manifest.json",
);
const localRoot = path.join(repositoryRoot, ".local");
const corpusRoot = path.join(localRoot, "presentation-workspace-corpus");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const records = manifest.records;
const supplementalRecords = manifest.supplemental_records ?? [];
const allRecords = [
  ...(Array.isArray(records) ? records : []),
  ...(Array.isArray(supplementalRecords) ? supplementalRecords : []),
];

function fail(message) {
  throw new Error(message);
}

function hash(buffer, algorithm) {
  return createHash(algorithm).update(buffer).digest("hex");
}

function normalizeTitle(value) {
  return value.normalize("NFC").trim().replace(/\s+/gu, " ");
}

function assertNoSymlink(target, label) {
  if (existsSync(target) && lstatSync(target).isSymbolicLink()) {
    fail(`${label} must not be a symlink.`);
  }
}

function ensureCacheDirectory() {
  assertNoSymlink(localRoot, "The .local cache root");
  mkdirSync(localRoot, { recursive: true });
  assertNoSymlink(localRoot, "The .local cache root");
  assertNoSymlink(corpusRoot, "The presentation corpus directory");
  mkdirSync(corpusRoot, { recursive: true });
  assertNoSymlink(corpusRoot, "The presentation corpus directory");
  const resolved = path.resolve(corpusRoot);
  const relative = path.relative(path.resolve(localRoot), resolved);
  if (
    relative === "" ||
    relative === "." ||
    relative === ".." ||
    relative.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relative)
  ) {
    fail("The corpus cache escaped the ignored .local directory.");
  }
}

function validateManifest() {
  if (
    manifest.schema_version !== 1 ||
    manifest.license_policy?.accepted_record_license !== "cc-by-4.0" ||
    manifest.license_policy?.accepted_access_right !== "open" ||
    !Array.isArray(records) ||
    !Number.isSafeInteger(manifest.record_count) ||
    records.length !== manifest.record_count ||
    !Array.isArray(supplementalRecords) ||
    !Number.isSafeInteger(manifest.supplemental_record_count) ||
    supplementalRecords.length !== manifest.supplemental_record_count
  ) {
    fail("The corpus manifest does not match the supported schema and scope.");
  }
  let aggregateBytes = 0;
  const names = new Set();
  const recordIds = new Set();
  for (const item of records) {
    if (
      !Number.isSafeInteger(item.record_id) ||
      typeof item.title !== "string" ||
      typeof item.doi !== "string" ||
      !/^10\.5281\/zenodo\.\d+$/.test(item.doi) ||
      typeof item.source_filename !== "string" ||
      !Array.isArray(item.creators) ||
      item.creators.length === 0 ||
      item.creators.some(
        (creator) => typeof creator !== "string" || !creator.trim(),
      ) ||
      !/^[a-f0-9]{32}$/.test(item.file_md5) ||
      !Number.isSafeInteger(item.file_size_bytes) ||
      item.file_size_bytes <= 0 ||
      item.file_size_bytes > manifest.max_file_size_bytes ||
      !/^[a-z0-9][a-z0-9.-]*\.pptx$/.test(item.local_name)
    ) {
      fail("A record entry in the corpus manifest is invalid.");
    }
    if (names.has(item.local_name))
      fail("Corpus local filenames must be unique.");
    if (recordIds.has(item.record_id))
      fail("Corpus record identifiers must be unique.");
    names.add(item.local_name);
    recordIds.add(item.record_id);
    aggregateBytes += item.file_size_bytes;
  }
  for (const item of supplementalRecords) {
    if (
      item.source_type !== "internet_archive" ||
      !Number.isSafeInteger(item.record_id) ||
      typeof item.archive_identifier !== "string" ||
      // Internet Archive identifiers can contain periods, but no path separators.
      !/^[a-z0-9][a-z0-9._-]{0,127}$/i.test(item.archive_identifier) ||
      typeof item.title !== "string" ||
      !Array.isArray(item.creators) ||
      item.creators.length === 0 ||
      item.creators.some(
        (creator) => typeof creator !== "string" || !creator.trim(),
      ) ||
      typeof item.source_filename !== "string" ||
      !/^[a-f0-9]{32}$/.test(item.file_md5) ||
      !/^[a-f0-9]{40}$/.test(item.file_sha1) ||
      (item.file_sha256 !== undefined &&
        !/^[a-f0-9]{64}$/.test(item.file_sha256)) ||
      !Number.isSafeInteger(item.file_size_bytes) ||
      item.file_size_bytes <= 0 ||
      item.file_size_bytes > manifest.max_file_size_bytes ||
      !/^[a-z0-9][a-z0-9.-]*\.pptx$/.test(item.local_name) ||
      item.archive_license_url !==
        "http://creativecommons.org/publicdomain/mark/1.0/"
    ) {
      fail("A supplemental Internet Archive entry is invalid.");
    }
    if (names.has(item.local_name))
      fail("Corpus local filenames must be unique.");
    if (recordIds.has(item.record_id))
      fail("Corpus record identifiers must be unique.");
    names.add(item.local_name);
    recordIds.add(item.record_id);
    aggregateBytes += item.file_size_bytes;
  }
  if (aggregateBytes > manifest.max_total_size_bytes) {
    fail("The corpus manifest exceeds its aggregate download limit.");
  }
}

async function getJson(url, sourceName = "Zenodo") {
  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "user-agent": "PresenterCopilotCorpusResearch/1.0",
    },
    signal: AbortSignal.timeout(45_000),
  });
  if (!response.ok)
    fail(`${sourceName} metadata request failed with HTTP ${response.status}.`);
  return response.json();
}

async function getBoundedFile(
  url,
  expectedSize,
  sourceName = "Zenodo",
  isAllowedFinalHost = () => true,
) {
  const headers = {
    // Zenodo's file endpoint requires this Accept value even though the
    // successful response body is the binary file.
    accept: "application/json",
    "user-agent": "PresenterCopilotCorpusResearch/1.0",
  };
  const signal = AbortSignal.timeout(120_000);
  let currentUrl = new URL(url);
  if (
    currentUrl.protocol !== "https:" ||
    currentUrl.username !== "" ||
    currentUrl.password !== "" ||
    !isAllowedFinalHost(currentUrl.hostname)
  ) {
    fail(`${sourceName} provided an unexpected download URL.`);
  }
  let response;
  for (let redirects = 0; redirects <= 5; redirects += 1) {
    response = await fetch(currentUrl, {
      headers,
      redirect: "manual",
      signal,
    });
    if (![301, 302, 303, 307, 308].includes(response.status)) break;
    const location = response.headers.get("location");
    const nextUrl = location ? new URL(location, currentUrl) : null;
    if (
      !nextUrl ||
      redirects === 5 ||
      nextUrl.protocol !== "https:" ||
      nextUrl.username !== "" ||
      nextUrl.password !== "" ||
      !isAllowedFinalHost(nextUrl.hostname)
    ) {
      await response.body?.cancel();
      fail(`${sourceName} redirected the download to an unexpected URL.`);
    }
    await response.body?.cancel();
    currentUrl = nextUrl;
  }
  if (!response) fail(`${sourceName} returned no download response.`);
  if (!response.ok)
    fail(`${sourceName} file request failed with HTTP ${response.status}.`);
  if (!response.body) fail(`${sourceName} returned an empty download stream.`);
  const contentLength = response.headers.get("content-length");
  if (contentLength && Number(contentLength) !== expectedSize) {
    fail(`${sourceName}'s download length did not match the pinned metadata.`);
  }

  const chunks = [];
  let byteLength = 0;
  const reader = response.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      byteLength += value.byteLength;
      if (byteLength > expectedSize) {
        await reader.cancel();
        fail(`${sourceName}'s download exceeded the pinned file size.`);
      }
      chunks.push(Buffer.from(value));
    }
  } finally {
    reader.releaseLock();
  }
  if (byteLength !== expectedSize)
    fail(`${sourceName}'s download ended before the pinned file size.`);
  return Buffer.concat(chunks, byteLength);
}

async function verifyRecord(item) {
  const record = await getJson(
    `https://zenodo.org/api/records/${item.record_id}`,
  );
  const metadata = record?.metadata;
  if (
    record?.id !== item.record_id ||
    metadata?.doi?.toLowerCase() !== item.doi.toLowerCase() ||
    typeof metadata?.title !== "string" ||
    normalizeTitle(metadata.title) !== normalizeTitle(item.title) ||
    metadata?.access_right !== manifest.license_policy.accepted_access_right ||
    metadata?.license?.id !== manifest.license_policy.accepted_record_license ||
    !Array.isArray(metadata.creators) ||
    JSON.stringify(
      metadata.creators.map((creator) => normalizeTitle(creator.name ?? "")),
    ) !== JSON.stringify(item.creators.map(normalizeTitle))
  ) {
    fail(
      `Zenodo record ${item.record_id} no longer matches its pinned rights metadata.`,
    );
  }
  const matchingFiles = (record.files ?? []).filter(
    (file) =>
      file.checksum === `md5:${item.file_md5}` &&
      file.size === item.file_size_bytes &&
      typeof file.key === "string" &&
      normalizeTitle(file.key) === normalizeTitle(item.source_filename) &&
      file.key.toLowerCase().endsWith(".pptx") &&
      typeof file.links?.self === "string",
  );
  if (matchingFiles.length !== 1) {
    fail(
      `Zenodo record ${item.record_id} does not have one exact matching PPTX file.`,
    );
  }
  const contentUrl = new URL(matchingFiles[0].links.self);
  if (
    contentUrl.protocol !== "https:" ||
    contentUrl.hostname !== "zenodo.org"
  ) {
    fail(
      `Zenodo record ${item.record_id} provided an unexpected download origin.`,
    );
  }
  const file = matchingFiles[0];
  return {
    source_type: "zenodo",
    source_identifier: item.doi,
    title: record.metadata.title,
    creators: record.metadata.creators.map((creator) => creator.name),
    source_filename: file.key,
    contentUrl: contentUrl.href,
    license_id: record.metadata.license.id,
    license_url: record.metadata.license.url,
  };
}

async function verifyInternetArchiveRecord(item) {
  const record = await getJson(
    `https://archive.org/metadata/${encodeURIComponent(item.archive_identifier)}`,
    "Internet Archive",
  );
  const metadata = record?.metadata;
  const creators = Array.isArray(metadata?.creator)
    ? metadata.creator.map(normalizeTitle)
    : typeof metadata?.creator === "string"
      ? [normalizeTitle(metadata.creator)]
      : [];
  if (
    metadata?.identifier !== item.archive_identifier ||
    typeof metadata?.title !== "string" ||
    normalizeTitle(metadata.title) !== normalizeTitle(item.title) ||
    metadata?.licenseurl !== item.archive_license_url ||
    JSON.stringify(creators) !==
      JSON.stringify(item.creators.map(normalizeTitle))
  ) {
    fail(
      `Internet Archive item ${item.archive_identifier} no longer matches its pinned rights metadata.`,
    );
  }
  const matchingFiles = (record.files ?? []).filter(
    (file) =>
      typeof file.name === "string" &&
      normalizeTitle(file.name) === normalizeTitle(item.source_filename) &&
      Number(file.size) === item.file_size_bytes &&
      typeof file.md5 === "string" &&
      file.md5.toLowerCase() === item.file_md5 &&
      typeof file.sha1 === "string" &&
      file.sha1.toLowerCase() === item.file_sha1 &&
      file.name.toLowerCase().endsWith(".pptx"),
  );
  if (matchingFiles.length !== 1) {
    fail(
      `Internet Archive item ${item.archive_identifier} does not have one exact matching PPTX file.`,
    );
  }
  const file = matchingFiles[0];
  const encodedPath = [item.archive_identifier, file.name]
    .map(encodeURIComponent)
    .join("/");
  return {
    source_type: "internet_archive",
    source_identifier: item.archive_identifier,
    title: metadata.title,
    creators,
    source_filename: file.name,
    contentUrl: `https://archive.org/download/${encodedPath}`,
    license_id: "public-domain-mark-1.0",
    license_url: metadata.licenseurl,
  };
}

function verifyExisting(item, destination) {
  if (!existsSync(destination)) return null;
  assertNoSymlink(destination, `Cached file ${item.local_name}`);
  const info = lstatSync(destination);
  if (!info.isFile() || info.size !== item.file_size_bytes) {
    fail(
      `Existing cache entry ${item.local_name} differs from the pinned file; it was left untouched.`,
    );
  }
  const bytes = readFileSync(destination);
  if (hash(bytes, "md5") !== item.file_md5) {
    fail(
      `Existing cache entry ${item.local_name} failed its MD5 check; it was left untouched.`,
    );
  }
  if (item.file_sha1 && hash(bytes, "sha1") !== item.file_sha1) {
    fail(
      `Existing cache entry ${item.local_name} failed its SHA-1 check; it was left untouched.`,
    );
  }
  if (item.file_sha256 && hash(bytes, "sha256") !== item.file_sha256) {
    fail(
      `Existing cache entry ${item.local_name} failed its SHA-256 check; it was left untouched.`,
    );
  }
  return { sha256: hash(bytes, "sha256"), cached: true };
}

async function cacheRecord(item) {
  const sourceInfo =
    item.source_type === "internet_archive"
      ? await verifyInternetArchiveRecord(item)
      : await verifyRecord(item);
  const destination = path.join(corpusRoot, item.local_name);
  const cached = verifyExisting(item, destination);
  if (cached) {
    return {
      record_id: item.record_id,
      source_type: sourceInfo.source_type,
      source_identifier: sourceInfo.source_identifier,
      doi: item.doi ?? null,
      title: sourceInfo.title,
      creators: sourceInfo.creators,
      source_filename: sourceInfo.source_filename,
      local_name: item.local_name,
      byte_size: item.file_size_bytes,
      md5: item.file_md5,
      sha256: cached.sha256,
      license_id: sourceInfo.license_id,
      license_url: sourceInfo.license_url,
      status: "already_verified",
    };
  }

  const sourceName =
    sourceInfo.source_type === "internet_archive"
      ? "Internet Archive"
      : "Zenodo";
  const bytes = await getBoundedFile(
    sourceInfo.contentUrl,
    item.file_size_bytes,
    sourceName,
    sourceInfo.source_type === "internet_archive"
      ? (hostname) =>
          hostname === "archive.org" || hostname.endsWith(".archive.org")
      : () => true,
  );
  if (hash(bytes, "md5") !== item.file_md5) {
    fail(`Downloaded file for record ${item.record_id} failed its MD5 check.`);
  }
  if (item.file_sha1 && hash(bytes, "sha1") !== item.file_sha1) {
    fail(
      `Downloaded file for record ${item.record_id} failed its SHA-1 check.`,
    );
  }
  if (item.file_sha256 && hash(bytes, "sha256") !== item.file_sha256) {
    fail(
      `Downloaded file for record ${item.record_id} failed its SHA-256 check.`,
    );
  }
  const temporaryPath = `${destination}.part-${randomUUID()}`;
  try {
    writeFileSync(temporaryPath, bytes, { flag: "wx" });
    const persisted = readFileSync(temporaryPath);
    if (
      persisted.length !== item.file_size_bytes ||
      hash(persisted, "md5") !== item.file_md5
    ) {
      fail(
        `Temporary cache entry for record ${item.record_id} failed verification.`,
      );
    }
    // A same-directory hard link publishes the complete verified file
    // atomically and fails if another run already created the destination.
    try {
      linkSync(temporaryPath, destination);
    } catch (error) {
      if (
        error &&
        typeof error === "object" &&
        "code" in error &&
        error.code === "EEXIST"
      ) {
        fail(
          `A concurrent run created ${item.local_name}; no file was overwritten.`,
        );
      }
      throw error;
    }
    unlinkSync(temporaryPath);
  } finally {
    if (existsSync(temporaryPath)) rmSync(temporaryPath);
  }
  const stored = readFileSync(destination);
  if (
    stored.length !== item.file_size_bytes ||
    hash(stored, "md5") !== item.file_md5
  ) {
    fail(
      `Cached file for record ${item.record_id} failed its final verification.`,
    );
  }
  return {
    record_id: item.record_id,
    source_type: sourceInfo.source_type,
    source_identifier: sourceInfo.source_identifier,
    doi: item.doi ?? null,
    title: sourceInfo.title,
    creators: sourceInfo.creators,
    source_filename: sourceInfo.source_filename,
    local_name: item.local_name,
    byte_size: item.file_size_bytes,
    md5: item.file_md5,
    sha256: hash(stored, "sha256"),
    license_id: sourceInfo.license_id,
    license_url: sourceInfo.license_url,
    status: "downloaded_and_verified",
  };
}

validateManifest();
ensureCacheDirectory();
const results = [];
for (const item of allRecords) results.push(await cacheRecord(item));

process.stdout.write(
  `${JSON.stringify(
    {
      status: "verified",
      cache_directory: path
        .relative(repositoryRoot, corpusRoot)
        .replaceAll("\\", "/"),
      record_count: results.length,
      zenodo_record_count: records.length,
      supplemental_record_count: supplementalRecords.length,
      total_bytes: results.reduce((total, item) => total + item.byte_size, 0),
      license_ids: [...new Set(results.map((item) => item.license_id))],
      metadata_rights_rechecked: true,
      results,
    },
    null,
    2,
  )}\n`,
);
