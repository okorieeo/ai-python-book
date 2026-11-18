import { describe, expect, it } from "vitest";
import {
  attachmentsReady, attachmentsReducer, formatBytes, messageFromResponse, uploadedIds,
  uploadFile, UploadError, validateBatch, validateFile, type Attachment, type XhrLike,
} from "./attachments";
import { removeFromList, renameInList } from "./conversations-cache";

const file = (name: string, size = 1000, type = "image/png") => ({ name, size, type });

describe("validateFile", () => {
  it("accepts allowed files", () => {
    expect(validateFile(file("photo.PNG"))).toBeNull();
    expect(validateFile(file("notes.md", 10, "text/markdown"))).toBeNull();
  });
  it("accepts a file whose browser type is empty (it happens) if the extension is allowed", () => {
    expect(validateFile(file("readme.md", 10, ""))).toBeNull();
  });
  it("rejects unsupported extensions and types", () => {
    expect(validateFile(file("run.exe", 10, "application/x-msdownload"))).toBe("This file type is not supported.");
    expect(validateFile(file("noextension", 10, "image/png"))).toBe("This file type is not supported.");
    expect(validateFile(file("fake.png", 10, "application/x-sh"))).toBe("This file type is not supported.");
  });
  it("rejects empty and oversized files", () => {
    expect(validateFile(file("a.png", 0))).toBe("This file is empty.");
    expect(validateFile(file("a.png", 10 * 1024 * 1024 + 1))).toBe("This file is larger than 10 MB.");
  });
});

describe("validateBatch", () => {
  it("accepts good files and explains each rejection", () => {
    const { accepted, rejected } = validateBatch(0, [file("a.png"), file("b.exe", 5, "x/y"), file("c.pdf", 5, "application/pdf")]);
    expect(accepted.map((f) => f.name)).toEqual(["a.png", "c.pdf"]);
    expect(rejected).toEqual([{ name: "b.exe", reason: "This file type is not supported." }]);
  });
  it("enforces the maximum count including files already attached", () => {
    const files = [file("1.png"), file("2.png"), file("3.png")];
    const { accepted, rejected } = validateBatch(3, files);
    expect(accepted).toHaveLength(2);
    expect(rejected).toEqual([{ name: "3.png", reason: "You can attach up to 5 files." }]);
  });
});

describe("formatBytes", () => {
  it("is readable", () => {
    expect([512, 2048, 10 * 1024 * 1024, 1.5 * 1024 * 1024].map(formatBytes)).toEqual(["512 B", "2 KB", "10 MB", "1.5 MB"]);
  });
});

describe("attachmentsReducer", () => {
  const add = { type: "add", item: { localId: "l1", name: "a.png", size: 5, type: "image/png" } } as const;
  const run = (...actions: Parameters<typeof attachmentsReducer>[1][]) =>
    actions.reduce(attachmentsReducer, [] as Attachment[]);

  it("walks through uploading to done", () => {
    const s = run(add, { type: "progress", localId: "l1", progress: 40 }, { type: "done", localId: "l1", uploadId: "u1" });
    expect(s[0]).toEqual({ localId: "l1", name: "a.png", size: 5, type: "image/png", status: "done", progress: 100, uploadId: "u1", error: undefined });
    expect(uploadedIds(s)).toEqual(["u1"]);
    expect(attachmentsReady(s)).toBe(true);
  });
  it("keeps progress within 0..100", () => {
    expect(run(add, { type: "progress", localId: "l1", progress: 250 })[0]?.progress).toBe(100);
    expect(run(add, { type: "progress", localId: "l1", progress: -5 })[0]?.progress).toBe(0);
  });
  it("blocks sending while an upload is running or failed, and allows retry", () => {
    const uploading = run(add);
    expect(attachmentsReady(uploading)).toBe(false);
    const failed = attachmentsReducer(uploading, { type: "fail", localId: "l1", error: "boom" });
    expect(failed[0]?.status).toBe("error");
    expect(attachmentsReady(failed)).toBe(false);
    const retried = attachmentsReducer(failed, { type: "retry", localId: "l1" });
    expect(retried[0]).toEqual({ ...failed[0], status: "uploading", progress: 0, error: undefined });
  });
  it("removes and clears", () => {
    expect(run(add, { type: "remove", localId: "l1" })).toEqual([]);
    expect(run(add, { type: "clear" })).toEqual([]);
  });
  it("an empty tray is ready to send", () => {
    expect(attachmentsReady([])).toBe(true);
  });
});

class FakeXhr implements XhrLike {
  method = ""; url = ""; headers: Record<string, string> = {}; body: FormData | null = null; aborted = false;
  withCredentials = false; status = 0; responseText = "";
  upload: XhrLike["upload"] = { onprogress: null };
  onload: (() => void) | null = null; onerror: (() => void) | null = null; onabort: (() => void) | null = null;
  open(m: string, u: string) { this.method = m; this.url = u; }
  setRequestHeader(n: string, v: string) { this.headers[n] = v; }
  send(b: FormData) { this.body = b; }
  abort() { this.aborted = true; this.onabort?.(); }
  respond(status: number, text: string) { this.status = status; this.responseText = text; this.onload?.(); }
}
const blob = () => Object.assign(new Blob(["hello"], { type: "text/plain" }), { name: "hello.txt" });

describe("uploadFile", () => {
  it("posts multipart form data and resolves with the server id", async () => {
    const xhr = new FakeXhr(); const progress: number[] = [];
    const promise = uploadFile(blob(), { url: "/api/v1/uploads/", headers: { Authorization: "Bearer t" }, onProgress: (p) => progress.push(p) }, () => xhr);
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 200 });
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 200, total: 200 });
    xhr.upload.onprogress?.({ lengthComputable: false, loaded: 0, total: 0 });
    xhr.respond(201, '{"id":"up_123","name":"hello.txt"}');
    expect(await promise).toEqual({ id: "up_123" });
    expect(progress).toEqual([25, 100]);
    expect(xhr.method).toBe("POST");
    expect(xhr.headers).toEqual({ Authorization: "Bearer t" }); // no Content-Type set by us
    expect((xhr.body?.get("file") as File).name).toBe("hello.txt");
  });
  it("turns server errors into readable messages", async () => {
    const cases: [number, string, string][] = [
      [400, '{"error":{"message":"Unsupported file type."}}', "Unsupported file type."],
      [403, '{"detail":"Not allowed."}', "Not allowed."],
      [413, "<html>too big</html>", "The file is too large."],
      [500, "oops", "Upload failed (500)."],
    ];
    for (const [status, text, message] of cases) {
      const xhr = new FakeXhr();
      const promise = uploadFile(blob(), { url: "/u" }, () => xhr);
      xhr.respond(status, text);
      await promise.then(() => { throw new Error("should fail"); }, (e: unknown) => {
        expect(e instanceof UploadError).toBe(true);
        expect((e as UploadError).message).toBe(message);
        expect((e as UploadError).status).toBe(status);
      });
    }
  });
  it("rejects a success response without an id", async () => {
    const xhr = new FakeXhr(); const promise = uploadFile(blob(), { url: "/u" }, () => xhr);
    xhr.respond(200, "{}");
    await promise.then(() => { throw new Error("should fail"); }, (e: unknown) => expect((e as Error).message).toBe("The server sent an unexpected response."));
  });
  it("reports network errors", async () => {
    const xhr = new FakeXhr(); const promise = uploadFile(blob(), { url: "/u" }, () => xhr);
    xhr.onerror?.();
    await promise.then(() => { throw new Error("should fail"); }, (e: unknown) => expect((e as Error).message).toContain("Network error"));
  });
  it("can be cancelled with an AbortSignal", async () => {
    const xhr = new FakeXhr(); const controller = new AbortController();
    const promise = uploadFile(blob(), { url: "/u", signal: controller.signal }, () => xhr);
    controller.abort();
    await promise.then(() => { throw new Error("should fail"); }, (e: unknown) => {
      expect(xhr.aborted).toBe(true);
      expect((e as UploadError).cancelled).toBe(true);
    });
  });
  it("does not even send when the signal is already aborted", async () => {
    const xhr = new FakeXhr(); const controller = new AbortController(); controller.abort();
    await uploadFile(blob(), { url: "/u", signal: controller.signal }, () => xhr)
      .then(() => { throw new Error("should fail"); }, (e: unknown) => expect((e as UploadError).cancelled).toBe(true));
    expect(xhr.body).toBeNull();
  });
});

describe("messageFromResponse", () => {
  it("finds the message in common shapes and returns null otherwise", () => {
    expect(messageFromResponse('{"message":"x"}')).toBe("x");
    expect(messageFromResponse("[]")).toBeNull();
    expect(messageFromResponse("not json")).toBeNull();
  });
});

describe("conversation list helpers (optimistic updates)", () => {
  const list = [{ id: "a", title: "A" }, { id: "b", title: "B" }];
  it("renames without touching the others or mutating the input", () => {
    const next = renameInList(list, "b", "Bee");
    expect(next).toEqual([{ id: "a", title: "A" }, { id: "b", title: "Bee" }]);
    expect(next[0]).toBe(list[0]);
    expect(list[1]?.title).toBe("B");
  });
  it("removes by id", () => {
    expect(removeFromList(list, "a")).toEqual([{ id: "b", title: "B" }]);
  });
});
