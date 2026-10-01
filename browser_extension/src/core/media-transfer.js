import { ERROR_CODE, SmartFlowBridgeError } from "./errors.js";

export class ChunkTransferStore {
  constructor({ maxBytes = 64 * 1024 * 1024, ttlMs = 5 * 60 * 1000 } = {}) {
    this.maxBytes = Math.max(1024, Number(maxBytes));
    this.ttlMs = Math.max(1000, Number(ttlMs));
    this.transfers = new Map();
  }

  cleanup(now = Date.now()) {
    for (const [id, transfer] of this.transfers) {
      if (now - transfer.updatedAt > this.ttlMs) this.transfers.delete(id);
    }
  }

  append({ transferId, sequence, totalChunks, chunk }) {
    this.cleanup();
    if (!/^[A-Za-z0-9_-]{6,120}$/.test(String(transferId || ""))) {
      throw new SmartFlowBridgeError(ERROR_CODE.INVALID_MESSAGE, "Invalid transfer id");
    }
    if (!Number.isInteger(sequence) || !Number.isInteger(totalChunks)
        || sequence < 0 || totalChunks < 1 || sequence >= totalChunks || totalChunks > 4096) {
      throw new SmartFlowBridgeError(ERROR_CODE.INVALID_MESSAGE, "Invalid chunk sequence");
    }
    const bytes = chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk);
    let transfer = this.transfers.get(transferId);
    if (!transfer) {
      transfer = { totalChunks, chunks: new Map(), bytes: 0, updatedAt: Date.now() };
      this.transfers.set(transferId, transfer);
    }
    if (transfer.totalChunks !== totalChunks) {
      throw new SmartFlowBridgeError(ERROR_CODE.INVALID_MESSAGE, "Chunk count changed during transfer");
    }
    const previous = transfer.chunks.get(sequence);
    transfer.bytes += bytes.byteLength - (previous?.byteLength || 0);
    if (transfer.bytes > this.maxBytes) {
      this.transfers.delete(transferId);
      throw new SmartFlowBridgeError(ERROR_CODE.UPLOAD_FAILED, "Media transfer exceeds size limit");
    }
    transfer.chunks.set(sequence, bytes);
    transfer.updatedAt = Date.now();
    return { received: transfer.chunks.size, totalChunks, bytes: transfer.bytes, complete: transfer.chunks.size === totalChunks };
  }

  consume(transferId) {
    const transfer = this.transfers.get(transferId);
    if (!transfer || transfer.chunks.size !== transfer.totalChunks) {
      throw new SmartFlowBridgeError(ERROR_CODE.TRANSFER_INCOMPLETE, "Media transfer is incomplete");
    }
    const output = new Uint8Array(transfer.bytes);
    let offset = 0;
    for (let index = 0; index < transfer.totalChunks; index += 1) {
      const chunk = transfer.chunks.get(index);
      if (!chunk) throw new SmartFlowBridgeError(ERROR_CODE.TRANSFER_INCOMPLETE, `Missing chunk ${index}`);
      output.set(chunk, offset);
      offset += chunk.byteLength;
    }
    this.transfers.delete(transferId);
    return output;
  }

  cancel(transferId) {
    return this.transfers.delete(transferId);
  }
}
