import { ERROR_CODE, SmartFlowBridgeError } from "./errors.js";

const delay = (milliseconds, signal) => new Promise((resolve, reject) => {
  if (signal?.aborted) {
    reject(new SmartFlowBridgeError(ERROR_CODE.CANCELLED, "Operation cancelled"));
    return;
  }
  const timer = setTimeout(resolve, milliseconds);
  signal?.addEventListener("abort", () => {
    clearTimeout(timer);
    reject(new SmartFlowBridgeError(ERROR_CODE.CANCELLED, "Operation cancelled"));
  }, { once: true });
});

export function isRetryableStatus(status) {
  const code = Number(status || 0);
  return code === 408 || code === 429 || (code >= 500 && code <= 599);
}

export async function withRetry(operation, options = {}) {
  const maxAttempts = Math.max(1, Math.min(10, Number(options.maxAttempts ?? 3)));
  const initialDelay = Math.max(0, Number(options.initialDelay ?? 500));
  const factor = Math.max(1, Number(options.factor ?? 2));
  const signal = options.signal;
  let lastError = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    if (signal?.aborted) throw new SmartFlowBridgeError(ERROR_CODE.CANCELLED, "Operation cancelled");
    try {
      return await operation({ attempt, signal });
    } catch (error) {
      lastError = error;
      const retryable = typeof options.shouldRetry === "function"
        ? Boolean(await options.shouldRetry(error, attempt))
        : Boolean(error?.retryable || isRetryableStatus(error?.status));
      if (!retryable || attempt >= maxAttempts || error?.code === ERROR_CODE.AUTH_REQUIRED) throw error;
      await delay(initialDelay * (factor ** (attempt - 1)), signal);
    }
  }
  throw lastError;
}
