import { EventEmitter } from "node:events";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { PassThrough, Writable } from "node:stream";

import { afterEach, describe, expect, it, vi } from "vitest";

import { CoreProcessClient, CoreRequestTimeoutError } from "./core-client";
import type { EventEnvelope } from "../shared/protocol";

const readyMessage: EventEnvelope = {
  protocol_version: 1,
  type: "event",
  event: "core.ready",
  payload: {
    protocol_version: 1,
    core_version: "0.1.0",
    capabilities: {
      methods: ["core.hello", "core.health", "core.shutdown"],
      events: ["core.ready", "core.error"],
    },
    adapters: [],
    migration_status: "not_required",
  },
};

class FakeChild extends EventEmitter {
  readonly stdout = new PassThrough();
  readonly stderr = new PassThrough();
  readonly writes: string[] = [];
  readonly stdin: Writable;
  killed = false;

  constructor() {
    super();
    this.stdin = new Writable({
      write: (chunk, _encoding, callback) => {
        const line = chunk.toString();
        this.writes.push(line);
        if (JSON.parse(line).method === "core.shutdown") {
          const requestId = JSON.parse(line).request_id as string;
          this.stdout.write(response(requestId, { status: "shutting_down" }));
          queueMicrotask(() => this.emit("exit", 0, null));
        }
        callback();
      },
    });
  }

  kill = vi.fn(() => {
    this.killed = true;
    this.emit("exit", null, "SIGTERM");
    return true;
  });
}

function makeClient(
  fakeChild: FakeChild,
  overrides: Record<string, unknown> = {},
) {
  return new CoreProcessClient({
    command: "fake-python",
    args: [],
    requestTimeoutMs: 100,
    startupTimeoutMs: 500,
    spawnProcess: () => fakeChild as unknown as ChildProcessWithoutNullStreams,
    ...overrides,
  });
}

async function startedClient() {
  const child = new FakeChild();
  const client = makeClient(child);
  const start = client.start();
  child.stdout.write(`${JSON.stringify(readyMessage)}\n`);
  await start;
  return { client, child };
}

function response(requestId: string, result: unknown): string {
  return `${JSON.stringify({
    protocol_version: 1,
    type: "response",
    request_id: requestId,
    ok: true,
    result,
  })}\n`;
}

afterEach(() => vi.useRealTimers());

describe("CoreProcessClient", () => {
  it("returns a rejecting promise when sidecar spawn fails synchronously", async () => {
    const client = new CoreProcessClient({
      command: "missing-python",
      spawnProcess: () => {
        throw new Error("spawn failed");
      },
    });

    await expect(client.start()).rejects.toMatchObject({
      code: "SIDECAR_START_FAILED",
    });
    expect(client.getStatus().state).toBe("unavailable");
  });

  it("accepts the shared cross-language protocol examples", () => {
    const fixturePath = path.resolve(
      __dirname,
      "../../../../shared/schemas/protocol-v1.examples.json",
    );
    const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as {
      protocol_version: number;
      messages: Array<Record<string, unknown>>;
    };

    expect(fixture.protocol_version).toBe(1);
    for (const message of fixture.messages) {
      expect(message.protocol_version).toBe(1);
      expect(["request", "response", "event"]).toContain(message.type);
      if (message.type === "response") {
        expect(typeof message.request_id === "string").toBe(true);
        expect(typeof message.ok).toBe("boolean");
      }
      if (message.type === "event") {
        expect(typeof message.event).toBe("string");
        expect(message.payload).toBeTypeOf("object");
      }
    }
  });

  it("buffers partial lines and handles multiple messages in one chunk", async () => {
    const { client, child } = await startedClient();
    const first = client.request("core.health");
    const second = client.request("core.hello");
    const requestIds = child.writes.map(
      (line) => JSON.parse(line).request_id as string,
    );

    const combined = `${response(requestIds[1]!, { name: "hello" })}${response(requestIds[0]!, { status: "ok" })}`;
    child.stdout.write(combined.slice(0, 17));
    child.stdout.write(combined.slice(17));

    await expect(first).resolves.toEqual({ status: "ok" });
    await expect(second).resolves.toEqual({ name: "hello" });
    await client.shutdown();
  });

  it("delivers events independently of responses", async () => {
    const { client, child } = await startedClient();
    const events: string[] = [];
    client.onEvent((event) => events.push(event.event));
    const requestPromise = client.request("core.health");
    const requestId = JSON.parse(child.writes[0]!).request_id as string;

    child.stdout.write(
      `${JSON.stringify({ protocol_version: 1, type: "event", event: "core.progress", payload: { step: 1 } })}\n`,
    );
    child.stdout.write(response(requestId, { status: "ok" }));

    await expect(requestPromise).resolves.toEqual({ status: "ok" });
    expect(events).toEqual(["core.progress"]);
    await client.shutdown();
  });

  it("survives malformed JSON and reports a structured core error response", async () => {
    const { client, child } = await startedClient();
    const protocolErrors: string[] = [];
    client.onProtocolError((error) => protocolErrors.push(error.code));
    child.stdout.write("not json\n");

    const requestPromise = client.request("core.health");
    const requestId = JSON.parse(child.writes[0]!).request_id as string;
    child.stdout.write(
      `${JSON.stringify({
        protocol_version: 1,
        type: "response",
        request_id: requestId,
        ok: false,
        error: {
          code: "METHOD_NOT_FOUND",
          message: "Unknown method",
          retryable: false,
          details: { method: "core.nope" },
        },
      })}\n`,
    );

    expect(protocolErrors).toEqual(["MALFORMED_JSON"]);
    await expect(requestPromise).rejects.toMatchObject({
      code: "METHOD_NOT_FOUND",
    });
    await client.shutdown();
  });

  it("rejects a request on timeout", async () => {
    vi.useFakeTimers();
    const { client } = await startedClient();
    const requestPromise = client.request("core.health");
    const rejection = expect(requestPromise).rejects.toBeInstanceOf(
      CoreRequestTimeoutError,
    );
    await vi.advanceTimersByTimeAsync(101);

    await rejection;
    await client.shutdown();
  });

  it("correlates an incompatible response version to its outstanding request", async () => {
    const { client, child } = await startedClient();
    const requestPromise = client.request("core.health");
    const requestId = JSON.parse(child.writes[0]!).request_id as string;
    child.stdout.write(
      `${JSON.stringify({
        protocol_version: 99,
        type: "response",
        request_id: requestId,
        ok: true,
        result: {},
      })}\n`,
    );

    await expect(requestPromise).rejects.toMatchObject({
      code: "PROTOCOL_VERSION_UNSUPPORTED",
    });
    await client.shutdown();
  });

  it("marks pending requests unavailable when the sidecar exits unexpectedly", async () => {
    const { client, child } = await startedClient();
    const requestPromise = client.request("core.health");
    child.emit("exit", 1, null);

    await expect(requestPromise).rejects.toMatchObject({
      code: "SIDECAR_EXITED_UNEXPECTEDLY",
    });
    expect(client.getStatus().state).toBe("unavailable");
  });
});
