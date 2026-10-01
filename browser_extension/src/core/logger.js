const SECRET_KEYS = /password|cookie|authorization|access[_-]?token|session[_-]?token|lease[_-]?token/i;

function redact(value, depth = 0) {
  if (depth > 5) return "[truncated]";
  if (Array.isArray(value)) return value.slice(0, 50).map((item) => redact(item, depth + 1));
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [
    key,
    SECRET_KEYS.test(key) ? "[redacted]" : redact(item, depth + 1)
  ]));
}

export class Logger {
  constructor(context = {}, sink = null) {
    this.context = { ...context };
    this.sink = typeof sink === "function" ? sink : null;
  }

  child(context = {}) {
    return new Logger({ ...this.context, ...context }, this.sink);
  }

  emit(level, message, details = {}) {
    const entry = redact({
      time: new Date().toISOString(),
      level,
      message: String(message || ""),
      ...this.context,
      ...details
    });
    const writer = level === "error" ? console.error : level === "warn" ? console.warn : console.log;
    writer("[SmartFlow Bridge]", entry);
    this.sink?.(entry);
    return entry;
  }

  debug(message, details) { return this.emit("debug", message, details); }
  info(message, details) { return this.emit("info", message, details); }
  warn(message, details) { return this.emit("warn", message, details); }
  error(message, details) { return this.emit("error", message, details); }
  progress(stage, percent, message, details = {}) {
    return this.emit("progress", message, { ...details, stage, percent: Math.max(0, Math.min(100, Number(percent || 0))) });
  }
}
