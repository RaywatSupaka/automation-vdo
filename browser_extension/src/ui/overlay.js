export class StatusOverlay {
  constructor(id = "smartflow-bridge-overlay") {
    this.id = id;
    this.host = null;
    this.shadow = null;
  }

  ensure() {
    if (this.host?.isConnected) return;
    this.host = document.createElement("div");
    this.host.id = this.id;
    this.shadow = this.host.attachShadow({ mode: "closed" });
    this.shadow.innerHTML = `<style>
      :host{all:initial}.box{position:fixed;right:18px;bottom:18px;z-index:2147483647;width:300px;
      padding:14px;border:1px solid #2bdcff;border-radius:14px;background:#071024ee;color:#fff;
      font:13px/1.45 system-ui,sans-serif;box-shadow:0 14px 44px #0008}.title{font-weight:800;font-size:15px}
      .subtitle{margin-top:4px;color:#b9c8e8}.track{height:5px;margin-top:10px;border-radius:9px;background:#1b2844;overflow:hidden}
      .fill{height:100%;width:0;background:linear-gradient(90deg,#28d8ff,#b536f4)}.error{border-color:#ff607d}</style>
      <div class="box"><div class="title"></div><div class="subtitle"></div><div class="track"><div class="fill"></div></div></div>`;
    document.documentElement.appendChild(this.host);
  }

  showLoading(title, subtitle = "") {
    this.ensure();
    this.shadow.querySelector(".box").classList.remove("error");
    this.shadow.querySelector(".title").textContent = String(title || "SmartFlow AI");
    this.shadow.querySelector(".subtitle").textContent = String(subtitle || "");
    this.host.hidden = false;
  }

  updateProgress(percent, message = "") {
    this.ensure();
    this.shadow.querySelector(".fill").style.width = `${Math.max(0, Math.min(100, Number(percent || 0)))}%`;
    if (message) this.shadow.querySelector(".subtitle").textContent = String(message);
  }

  showError(message) {
    this.showLoading("SmartFlow AI • เกิดข้อผิดพลาด", message);
    this.shadow.querySelector(".box").classList.add("error");
  }

  hide() {
    if (this.host) this.host.hidden = true;
  }
}
