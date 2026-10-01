export const ERROR_CODE = Object.freeze({
  AUTH_REQUIRED: "AUTH_REQUIRED",
  TAB_NOT_FOUND: "TAB_NOT_FOUND",
  PAGE_NOT_READY: "PAGE_NOT_READY",
  ELEMENT_NOT_FOUND: "ELEMENT_NOT_FOUND",
  UPLOAD_FAILED: "UPLOAD_FAILED",
  API_ERROR: "API_ERROR",
  RATE_LIMITED: "RATE_LIMITED",
  TIMEOUT: "TIMEOUT",
  CANCELLED: "CANCELLED",
  UNSUPPORTED_ACTION: "UNSUPPORTED_ACTION",
  CONTENT_SCRIPT_STALE: "CONTENT_SCRIPT_STALE",
  BRIDGE_DISCONNECTED: "BRIDGE_DISCONNECTED",
  INVALID_MESSAGE: "INVALID_MESSAGE",
  DUPLICATE_JOB: "DUPLICATE_JOB",
  SECURITY_REJECTED: "SECURITY_REJECTED",
  TRANSFER_INCOMPLETE: "TRANSFER_INCOMPLETE"
});

export class SmartFlowBridgeError extends Error {
  constructor(code, message, details = {}) {
    super(String(message || code || "SmartFlow Bridge error"));
    this.name = "SmartFlowBridgeError";
    this.code = ERROR_CODE[code] || code || ERROR_CODE.API_ERROR;
    this.details = details && typeof details === "object" ? details : {};
  }
}

export function asBridgeError(error, fallbackCode = ERROR_CODE.API_ERROR) {
  if (error instanceof SmartFlowBridgeError) return error;
  return new SmartFlowBridgeError(
    error?.code || fallbackCode,
    error?.message || String(error || "Unknown error")
  );
}

export function serialiseError(error) {
  const resolved = asBridgeError(error);
  return {
    code: resolved.code,
    message: resolved.message,
    details: resolved.details
  };
}
