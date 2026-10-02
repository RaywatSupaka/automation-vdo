import { ERROR_CODE, SmartFlowBridgeError } from "./errors.js";

export async function runWithTimeout(operation, milliseconds, action) {
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
