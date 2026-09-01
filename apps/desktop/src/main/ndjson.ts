import { StringDecoder } from "node:string_decoder";

export class NdjsonLineBuffer {
  private decoder = new StringDecoder("utf8");
  private buffered = "";

  reset(): void {
    this.decoder = new StringDecoder("utf8");
    this.buffered = "";
  }

  push(chunk: Buffer | string): string[] {
    const bytes =
      typeof chunk === "string" ? Buffer.from(chunk, "utf8") : chunk;
    this.buffered += this.decoder.write(bytes);
    const lines: string[] = [];
    let newlineIndex = this.buffered.indexOf("\n");

    while (newlineIndex !== -1) {
      const line = this.buffered.slice(0, newlineIndex).replace(/\r$/, "");
      this.buffered = this.buffered.slice(newlineIndex + 1);
      if (line.length > 0) lines.push(line);
      newlineIndex = this.buffered.indexOf("\n");
    }

    return lines;
  }

  finish(): string[] {
    this.buffered += this.decoder.end();
    const line = this.buffered.replace(/\r$/, "");
    this.buffered = "";
    return line.length > 0 ? [line] : [];
  }
}
