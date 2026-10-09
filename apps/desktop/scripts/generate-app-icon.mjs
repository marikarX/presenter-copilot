import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { deflateSync } from "node:zlib";

const desktopRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const iconSizes = [16, 24, 32, 48, 64, 128, 256];
const iconPath = resolve(desktopRoot, "build/icon.ico");
const faviconPath = resolve(desktopRoot, "src/renderer/public/icon.png");

function insideRoundedRect(x, y, left, top, right, bottom, radius) {
  const nearestX = Math.max(left + radius, Math.min(right - radius, x));
  const nearestY = Math.max(top + radius, Math.min(bottom - radius, y));
  return Math.hypot(x - nearestX, y - nearestY) <= radius;
}

function renderIcon(size) {
  const scale = 4;
  const sampleCount = scale * scale;
  const highSize = size * scale;
  const pixels = Buffer.alloc(size * size * 4);
  const barXs = [0.31, 0.405, 0.5, 0.595, 0.69];
  const barHeights = [0.17, 0.27, 0.36, 0.27, 0.17];

  for (let py = 0; py < size; py += 1) {
    for (let px = 0; px < size; px += 1) {
      let red = 0;
      let green = 0;
      let blue = 0;
      let alpha = 0;

      for (let sy = 0; sy < scale; sy += 1) {
        for (let sx = 0; sx < scale; sx += 1) {
          const x = (px * scale + sx + 0.5) / highSize;
          const y = (py * scale + sy + 0.5) / highSize;
          const inTile = insideRoundedRect(
            x,
            y,
            0.025,
            0.025,
            0.975,
            0.975,
            0.2,
          );

          if (!inTile) continue;

          const gradient = Math.min(1, Math.max(0, y / 0.95));
          let sampleRed = Math.round(141 + (96 - 141) * gradient);
          let sampleGreen = Math.round(132 + (86 - 132) * gradient);
          let sampleBlue = Math.round(189 + (140 - 189) * gradient);
          const inCard = insideRoundedRect(x, y, 0.17, 0.2, 0.83, 0.8, 0.07);

          if (inCard) {
            sampleRed = 255;
            sampleGreen = 255;
            sampleBlue = 255;

            const inHeader =
              Math.abs(y - 0.315) <= 0.009 && x >= 0.25 && x <= 0.48;
            let inWave = false;

            for (let index = 0; index < barXs.length; index += 1) {
              const halfHeight = barHeights[index] / 2;
              if (
                Math.abs(x - barXs[index]) <= 0.014 &&
                y >= 0.59 - halfHeight &&
                y <= 0.59 + halfHeight
              ) {
                inWave = true;
                break;
              }
            }

            if (inHeader) {
              sampleRed = 214;
              sampleGreen = 209;
              sampleBlue = 234;
            }
            if (inWave) {
              sampleRed = 112;
              sampleGreen = 100;
              sampleBlue = 170;
            }
          }

          red += sampleRed;
          green += sampleGreen;
          blue += sampleBlue;
          alpha += 255;
        }
      }

      const offset = (py * size + px) * 4;
      pixels[offset] = Math.round(red / sampleCount);
      pixels[offset + 1] = Math.round(green / sampleCount);
      pixels[offset + 2] = Math.round(blue / sampleCount);
      pixels[offset + 3] = Math.round(alpha / sampleCount);
    }
  }

  return pixels;
}

const crcTable = new Uint32Array(256);
for (let index = 0; index < crcTable.length; index += 1) {
  let value = index;
  for (let bit = 0; bit < 8; bit += 1) {
    value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  }
  crcTable[index] = value >>> 0;
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const typeBytes = Buffer.from(type, "ascii");
  const checksumInput = Buffer.concat([typeBytes, data]);
  const chunk = Buffer.alloc(12 + data.length);
  chunk.writeUInt32BE(data.length, 0);
  typeBytes.copy(chunk, 4);
  data.copy(chunk, 8);
  chunk.writeUInt32BE(crc32(checksumInput), 8 + data.length);
  return chunk;
}

function encodePng(size, rgba) {
  const rowLength = size * 4;
  const raw = Buffer.alloc((rowLength + 1) * size);
  for (let row = 0; row < size; row += 1) {
    const start = row * (rowLength + 1);
    raw[start] = 0;
    rgba.copy(raw, start + 1, row * rowLength, (row + 1) * rowLength);
  }

  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header[8] = 8;
  header[9] = 6;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk("IHDR", header),
    pngChunk("IDAT", deflateSync(raw, { level: 9 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function encodeDib(size, rgba) {
  const pixelBytes = size * size * 4;
  const maskStride = Math.ceil(size / 32) * 4;
  const maskBytes = maskStride * size;
  const dib = Buffer.alloc(40 + pixelBytes + maskBytes);
  dib.writeUInt32LE(40, 0);
  dib.writeInt32LE(size, 4);
  dib.writeInt32LE(size * 2, 8);
  dib.writeUInt16LE(1, 12);
  dib.writeUInt16LE(32, 14);
  dib.writeUInt32LE(0, 16);
  dib.writeUInt32LE(pixelBytes + maskBytes, 20);

  let target = 40;
  for (let y = size - 1; y >= 0; y -= 1) {
    for (let x = 0; x < size; x += 1) {
      const source = (y * size + x) * 4;
      dib[target] = rgba[source + 2];
      dib[target + 1] = rgba[source + 1];
      dib[target + 2] = rgba[source];
      dib[target + 3] = rgba[source + 3];
      target += 4;
    }
  }

  const maskStart = 40 + pixelBytes;
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const source = (y * size + x) * 4;
      if (rgba[source + 3] === 0) {
        const maskOffset = maskStart + y * maskStride + (x >>> 3);
        dib[maskOffset] |= 1 << (7 - (x & 7));
      }
    }
  }
  return dib;
}

function encodeIco(images) {
  const headerSize = 6 + images.length * 16;
  const header = Buffer.alloc(headerSize);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);

  let offset = headerSize;
  images.forEach(({ size, dib }, index) => {
    const entry = 6 + index * 16;
    header[entry] = size === 256 ? 0 : size;
    header[entry + 1] = size === 256 ? 0 : size;
    header[entry + 2] = 0;
    header[entry + 3] = 0;
    header.writeUInt16LE(1, entry + 4);
    header.writeUInt16LE(32, entry + 6);
    header.writeUInt32LE(dib.length, entry + 8);
    header.writeUInt32LE(offset, entry + 12);
    offset += dib.length;
  });

  return Buffer.concat([header, ...images.map(({ dib }) => dib)]);
}

const images = iconSizes.map((size) => {
  const rgba = renderIcon(size);
  return { size, dib: encodeDib(size, rgba), rgba };
});
const ico = encodeIco(images);
const favicon = encodePng(256, images.at(-1).rgba);

await mkdir(resolve(desktopRoot, "build"), { recursive: true });
await mkdir(resolve(desktopRoot, "src/renderer/public"), { recursive: true });
await Promise.all([writeFile(iconPath, ico), writeFile(faviconPath, favicon)]);
process.stdout.write(
  `Generated ${iconPath} (${ico.length} bytes) and ${faviconPath} (${favicon.length} bytes)\n`,
);
