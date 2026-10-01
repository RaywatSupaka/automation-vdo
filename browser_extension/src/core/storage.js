export class ScopedStateStore {
  constructor({ session = chrome.storage.session, durable = chrome.storage.local, prefix = "smartflow:v2:" } = {}) {
    this.session = session || durable;
    this.durable = durable;
    this.prefix = prefix;
  }

  key(scope, id) {
    return `${this.prefix}${String(scope || "core")}:${String(id || "default")}`;
  }

  async setSession(scope, id, value, ttlMs = 30 * 60 * 1000) {
    const key = this.key(scope, id);
    await this.session.set({ [key]: { value, expiresAt: Date.now() + Math.max(1000, Number(ttlMs || 0)) } });
    return key;
  }

  async getSession(scope, id) {
    const key = this.key(scope, id);
    const record = (await this.session.get(key))[key];
    if (!record) return null;
    if (Number(record.expiresAt || 0) <= Date.now()) {
      await this.session.remove(key);
      return null;
    }
    return record.value ?? null;
  }

  async removeSession(scope, id) {
    await this.session.remove(this.key(scope, id));
  }

  async setDurable(scope, id, value) {
    const key = this.key(scope, id);
    await this.durable.set({ [key]: value });
    return key;
  }

  async getDurable(scope, id) {
    const key = this.key(scope, id);
    return (await this.durable.get(key))[key] ?? null;
  }
}
