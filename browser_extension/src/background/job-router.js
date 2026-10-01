import { ERROR_CODE, SmartFlowBridgeError, serialiseError } from "../core/errors.js";
import { validateJobCommand } from "../core/message-schema.js";

async function runWithTimeout(operation, milliseconds, action) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      reject(new SmartFlowBridgeError(ERROR_CODE.TIMEOUT, `${action} timed out`));
    }, milliseconds);
  });

  try {
    return await Promise.race([operation, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

export class JobRouter {
  constructor({ defaultTimeoutMs = 180000, duplicateTtlMs = 10 * 60 * 1000, logger = null } = {}) {
    this.handlers = new Map();
    this.inflight = new Map();
    this.completed = new Map();
    this.defaultTimeoutMs = defaultTimeoutMs;
    this.duplicateTtlMs = duplicateTtlMs;
    this.logger = logger;
  }

  register(action, handler, options = {}) {
    if (!/^[a-z][a-z0-9_]{1,119}$/i.test(String(action || ""))) {
      throw new SmartFlowBridgeError(ERROR_CODE.INVALID_MESSAGE, "Invalid action name");
    }
    if (typeof handler !== "function") {
      throw new SmartFlowBridgeError(ERROR_CODE.INVALID_MESSAGE, `Handler missing for ${action}`);
    }
    if (this.handlers.has(action)) {
      throw new SmartFlowBridgeError(ERROR_CODE.INVALID_MESSAGE, `Handler already registered for ${action}`);
    }
    this.handlers.set(action, {
      handler,
      timeoutMs: Math.max(1000, Number(options.timeoutMs || this.defaultTimeoutMs)),
      platform: String(options.platform || "core")
    });
    return this;
  }

  registerAdapter(adapter) {
    for (const action of adapter.actions || []) {
      this.register(action, (job, context) => adapter.execute(action, job, context), {
        platform: adapter.id,
        timeoutMs: adapter.timeoutMs
      });
    }
    return this;
  }

  assertRegistered(command) {
    validateJobCommand(command);
    if (!this.handlers.has(command.action)) {
      throw new SmartFlowBridgeError(ERROR_CODE.UNSUPPORTED_ACTION, `No handler registered for ${command.action}`);
    }
    return command;
  }

  cleanup(now = Date.now()) {
    for (const [id, record] of this.completed) {
      if (now - record.completedAt > this.duplicateTtlMs) this.completed.delete(id);
    }
  }

  async dispatch(command, context = {}) {
    this.cleanup();
    const job = this.assertRegistered(command);
    const requestId = String(job.id);
    if (this.completed.has(requestId)) return this.completed.get(requestId).result;
    if (this.inflight.has(requestId)) return this.inflight.get(requestId);
    const route = this.handlers.get(job.action);
    const operation = (async () => {
      try {
        this.logger?.info("job_started", { jobId: job.job_id, requestId, action: job.action, platform: route.platform });
        const data = await runWithTimeout(
          route.handler(job, context),
          route.timeoutMs,
          job.action
        );
        const result = { type: "result", id: requestId, ok: true, data: data || {} };
        this.completed.set(requestId, { result, completedAt: Date.now() });
        return result;
      } catch (error) {
        const result = { type: "result", id: requestId, ok: false, error: serialiseError(error) };
        this.completed.set(requestId, { result, completedAt: Date.now() });
        return result;
      } finally {
        this.inflight.delete(requestId);
      }
    })();
    this.inflight.set(requestId, operation);
    return operation;
  }
}
