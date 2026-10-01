import { ALL_ACTIONS, EXTENSION_NAMESPACE, FLOW_EVIDENCE_NAMESPACE } from "./constants.js";
import { ERROR_CODE, SmartFlowBridgeError } from "./errors.js";

const isObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const boundedString = (value, max = 500) => typeof value === "string" && value.length > 0 && value.length <= max;

export function validateJobCommand(value) {
  if (!isObject(value)) {
    throw new SmartFlowBridgeError(ERROR_CODE.INVALID_MESSAGE, "Job command must be an object");
  }
  if (!boundedString(String(value.id || ""), 120)) {
    throw new SmartFlowBridgeError(ERROR_CODE.INVALID_MESSAGE, "Job command is missing request id");
  }
  if (!boundedString(String(value.action || ""), 120) || !ALL_ACTIONS.includes(value.action)) {
    throw new SmartFlowBridgeError(ERROR_CODE.UNSUPPORTED_ACTION, `Unsupported action: ${String(value.action || "")}`);
  }
  if (!boundedString(String(value.client_id || ""), 200)
      || !boundedString(String(value.run_id || ""), 120)
      || !boundedString(String(value.lease_token || ""), 160)) {
    throw new SmartFlowBridgeError(
      ERROR_CODE.INVALID_MESSAGE,
      "Job command requires client_id, run_id and lease_token"
    );
  }
  const shotIndex = Number(value.shot_index || 0);
  if (!Number.isInteger(shotIndex) || shotIndex < 0 || shotIndex > 50) {
    throw new SmartFlowBridgeError(ERROR_CODE.INVALID_MESSAGE, "Shot index is outside 0-50");
  }
  return value;
}

export function validatePageMessage(event, expectedType = "FLOW_MEDIA_EVIDENCE") {
  if (!event || event.source !== window || !isObject(event.data)) return null;
  const message = event.data;
  if (message.__smartFlow !== true || message.namespace !== FLOW_EVIDENCE_NAMESPACE) return null;
  if (message.type !== expectedType || !boundedString(String(message.requestId || ""), 160)) return null;
  if (!isObject(message.payload)) return null;
  return message;
}

export function makePageMessage(type, requestId, payload) {
  return {
    __smartFlow: true,
    namespace: FLOW_EVIDENCE_NAMESPACE,
    channel: "page",
    requestId,
    type,
    payload
  };
}

export function makeResultEnvelope(id, ok, data = {}, error = null) {
  const result = { namespace: EXTENSION_NAMESPACE, type: "result", id: String(id || ""), ok: Boolean(ok) };
  if (ok) result.data = isObject(data) ? data : { value: data };
  else result.error = error;
  return result;
}
