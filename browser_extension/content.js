(() => {
  if (window.__smartPostAffiliateLoaded) return;
  window.__smartPostAffiliateLoaded = true;

  const state = { products: new Map(), selected: new Set(), scanTimer: null };
  const clean = (value) => String(value || "").trim().replace(/\s+/g, " ");
  const absolute = (value) => {
    try { return new URL(value, location.href).href; } catch { return ""; }
  };
  const normalizedImageUrl = (value) => {
    if (!String(value || "").trim()) return "";
    try {
      const parsed = new URL(value, location.href);
      if (parsed.hostname.endsWith("img.susercontent.com")) {
        parsed.pathname = parsed.pathname.replace(/_tn$/i, "").replace(/@[^/]+$/i, "");
        parsed.search = "";
      }
      return parsed.href;
    } catch { return ""; }
  };
  const idsFromUrl = (url) => {
    for (const pattern of [/[?&](?:itemId|item_id)=(\d+)/i, /-i\.(\d+)\.(\d+)/i, /\/product\/(\d+)\/(\d+)/i, /\/opaanlp\/(\d+)\/(\d+)/i]) {
      const match = url.match(pattern);
      if (match) return match.length > 2 ? { shop_id: match[1], product_id: match[2] } : { shop_id: "", product_id: match[1] };
    }
    return { shop_id: "", product_id: "" };
  };
  const pickText = (root, selectors) => {
    for (const selector of selectors) {
      const element = root.querySelector(selector);
      const value = clean(element?.content || element?.textContent);
      if (value) return value;
    }
    return "";
  };
  const productImages = (root) => [...new Set([...root.querySelectorAll("img")]
    .filter((image) => {
      const rect = image.getBoundingClientRect();
      let node = image;
      while (node && node !== document.documentElement) {
        if (getComputedStyle(node).position === "fixed") return false;
        node = node.parentElement;
      }
      // A recommendation/review linked to a different product is not a
      // reference for the current detail page. Keep the card importer scoped.
      if (root === document) {
        const current = idsFromUrl(document.querySelector('link[rel="canonical"]')?.href || location.href);
        const linked = idsFromUrl(image.closest('a[href]')?.href || "");
        if (current.product_id && linked.product_id && current.product_id !== linked.product_id) return false;
      }
      // A real product photo can also be absolutely positioned or have a
      // promotional alt label. Leave pixel/alpha inspection to the desktop;
      // those layout/text hints alone must never discard a product image.
      return rect.width >= 70 && rect.height >= 70;
    })
    .map((image) => image.currentSrc || image.src || image.getAttribute("data-src") || "")
    .map(normalizedImageUrl)
    .filter((url) => url.startsWith("https://") && /img\.susercontent\.com\/file\//i.test(url) && !/avatar|icon|logo|qrcode|qr-code/i.test(url)))]
    .slice(0, 10);

  function productFromCard(card) {
    const links = [...card.querySelectorAll("a[href]")];
    const link = links.find((item) => /shopee\.co\.th|item|product|offer/i.test(item.href)) || links[0];
    const productUrl = absolute(link?.href || "");
    const images = productImages(card);
    const imageAlt = clean(card.querySelector("img")?.alt);
    const name = pickText(card, ['[class*="product-name"]', '[class*="item-name"]', '[class*="title"]', "h3", "h4"]) || imageAlt;
    if (!name || name.length < 3 || !images.length) return null;
    const allText = clean(card.innerText);
    const price = (allText.match(/฿\s?[\d,.]+(?:\s?[-–]\s?฿?\s?[\d,.]+)?/) || [""])[0];
    const commission = (allText.match(/(?:คอมมิชชัน|ค่าคอม|commission)[^\d%]{0,15}[\d,.]+\s?%?/i) || [""])[0];
    const ids = idsFromUrl(productUrl);
    const key = ids.product_id ? `${ids.shop_id}:${ids.product_id}` : `${productUrl}|${name}`;
    return {
      key,
      ...ids,
      product_name: name.slice(0, 500),
      price,
      commission,
      description: allText.slice(0, 4000),
      product_url: productUrl || location.href,
      affiliate_url: productUrl || location.href,
      images,
      captured_at: new Date().toISOString()
    };
  }

  function candidateCards() {
    const selectors = [
      '[class*="product-card"]', '[class*="product-item"]', '[class*="offer-card"]',
      '[class*="productCard"]', '[class*="ProductCard"]', 'tbody tr'
    ];
    const candidates = new Set(document.querySelectorAll(selectors.join(",")));
    document.querySelectorAll('a[href*="shopee.co.th"],a[href*="item"],a[href*="product"]').forEach((link) => {
      const card = link.closest('[class*="card"],[class*="item"],[class*="product"],li,tr');
      if (card && card !== document.body) candidates.add(card);
    });
    return [...candidates].filter((card) => card.querySelector("img") && card.getBoundingClientRect().width > 120);
  }

  function ensureStyle() {
    if (document.getElementById("smartpost-style")) return;
    const style = document.createElement("style"); style.id = "smartpost-style";
    style.textContent = `
      .smartpost-card-control{position:absolute!important;z-index:9990;top:8px;right:8px;display:flex;gap:6px;align-items:center;background:#0b1024e8;color:#fff;border:1px solid #3d55a0;border-radius:9px;padding:6px 8px;box-shadow:0 5px 16px #0005;font:600 12px Segoe UI,sans-serif}
      .smartpost-card-control input{accent-color:#8d38ee;width:15px;height:15px}
      .smartpost-card-control button{border:0;border-radius:6px;background:linear-gradient(135deg,#3978ff,#ad37ee);color:#fff;padding:5px 8px;cursor:pointer;font:600 11px Segoe UI,sans-serif}
      #smartpost-toolbar{position:fixed;z-index:2147483646;right:20px;bottom:20px;width:285px;background:#0b1024f5;color:#fff;border:1px solid #364675;border-radius:15px;box-shadow:0 15px 45px #0008;padding:14px;font-family:Segoe UI,sans-serif}
      #smartpost-toolbar strong{display:block;font-size:14px}#smartpost-toolbar small{display:block;color:#94a7d1;margin:3px 0 11px}
      #smartpost-toolbar .sp-actions{display:flex;gap:7px}#smartpost-toolbar button{flex:1;border:0;border-radius:8px;padding:8px;cursor:pointer;font-weight:650}
      #smartpost-import-selected{background:linear-gradient(135deg,#3978ff,#ad37ee);color:#fff}#smartpost-select-all{background:#1b274a;color:#dce6ff}
      #smartpost-toast{position:fixed;z-index:2147483647;left:50%;bottom:28px;transform:translateX(-50%);background:#111a32;color:#fff;border:1px solid #40538b;border-radius:10px;padding:10px 15px;box-shadow:0 8px 30px #0008;font:600 13px Segoe UI,sans-serif}
    `;
    document.documentElement.appendChild(style);
  }

  function ensureToolbar() {
    let toolbar = document.getElementById("smartpost-toolbar");
    if (!toolbar) {
      toolbar = document.createElement("div"); toolbar.id = "smartpost-toolbar";
      toolbar.innerHTML = `<strong>SmartPost Affiliate Importer</strong><small id="smartpost-count">กำลังตรวจสินค้า...</small><div class="sp-actions"><button id="smartpost-select-all">เลือกทั้งหมด</button><button id="smartpost-import-selected">นำเข้าที่เลือก</button></div>`;
      document.body.appendChild(toolbar);
      toolbar.querySelector("#smartpost-select-all").addEventListener("click", () => {
        const shouldSelect = state.selected.size !== state.products.size;
        state.selected.clear();
        if (shouldSelect) state.products.forEach((_, key) => state.selected.add(key));
        document.querySelectorAll(".smartpost-select").forEach((box) => { box.checked = shouldSelect; });
        updateCount();
      });
      toolbar.querySelector("#smartpost-import-selected").addEventListener("click", () => importProducts([...state.selected].map((key) => state.products.get(key)).filter(Boolean)));
    }
    updateCount();
  }

  function updateCount() {
    const count = document.getElementById("smartpost-count");
    if (count) count.textContent = `พบ ${state.products.size} สินค้า • เลือก ${state.selected.size}`;
  }

  function toast(message) {
    document.getElementById("smartpost-toast")?.remove();
    const element = document.createElement("div"); element.id = "smartpost-toast"; element.textContent = message; document.body.appendChild(element);
    setTimeout(() => element.remove(), 4200);
  }

  async function importProducts(products) {
    if (!products.length) { toast("กรุณาเลือกสินค้าอย่างน้อย 1 รายการ"); return; }
    toast(`กำลังส่ง ${products.length} สินค้าเข้าโปรแกรม...`);
    const response = await chrome.runtime.sendMessage({ type: "IMPORT_PRODUCTS", products });
    const success = response?.results?.filter((item) => item.ok).length || 0;
    const created = response?.results?.filter((item) => item.ok && item.created).length || 0;
    toast(`สำเร็จ ${success}/${products.length} • สร้างใหม่ ${created} รายการ`);
  }

  function decorate(card, product) {
    if (card.dataset.smartpostDecorated) return;
    card.dataset.smartpostDecorated = "1";
    if (getComputedStyle(card).position === "static") card.style.position = "relative";
    const control = document.createElement("div"); control.className = "smartpost-card-control";
    const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.className = "smartpost-select";
    checkbox.addEventListener("click", (event) => event.stopPropagation());
    checkbox.addEventListener("change", () => { checkbox.checked ? state.selected.add(product.key) : state.selected.delete(product.key); updateCount(); });
    const button = document.createElement("button"); button.textContent = "นำเข้า";
    button.addEventListener("click", (event) => { event.preventDefault(); event.stopPropagation(); importProducts([product]); });
    control.append(checkbox, button); card.appendChild(control);
  }

  function scanCards() {
    if (!location.pathname.includes("product_offer")) return;
    ensureStyle();
    const found = new Map();
    candidateCards().forEach((card) => {
      const product = productFromCard(card);
      if (!product || found.has(product.key)) return;
      found.set(product.key, product); decorate(card, product);
    });
    state.products = found;
    ensureToolbar(); updateCount();
  }

  const observer = new MutationObserver(() => {
    clearTimeout(state.scanTimer); state.scanTimer = setTimeout(scanCards, 700);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  scanCards();
  const extensionTickTimer = setInterval(() => {
    try {
      if (!chrome?.runtime?.id) {
        clearInterval(extensionTickTimer);
        observer.disconnect();
        return;
      }
      const pending = chrome.runtime.sendMessage({ type: "EXTENSION_TICK" });
      if (pending?.catch) pending.catch(() => {});
    } catch (_error) {
      clearInterval(extensionTickTimer);
      observer.disconnect();
    }
  }, 5000);

  const findJoinButton = () => [...document.querySelectorAll("a,button")].find((element) => clean(element.textContent) === "เข้าร่วมเลย");
  const structuredProduct = (canonical) => {
    const current = idsFromUrl(canonical);
    for (const script of [...document.querySelectorAll('script[type="application/ld+json"]')].slice(0, 12)) {
      let data;
      try { data = JSON.parse(script.textContent || ""); } catch { continue; }
      const roots = Array.isArray(data) ? data : [data];
      const entries = roots.flatMap((root) => [root, ...(Array.isArray(root?.['@graph']) ? root['@graph'] : [])]);
      for (const entry of entries) {
        if (!entry || ![entry['@type']].flat().some((type) => /(?:^|\/)Product$/i.test(String(type || "")))) continue;
        const linked = idsFromUrl(String(entry.url || ""));
        if (current.product_id && linked.product_id && current.product_id !== linked.product_id) continue;
        const offer = Array.isArray(entry.offers) ? entry.offers[0] : entry.offers;
        return { name: clean(entry.name), description: clean(entry.description).slice(0, 4000),
          price: clean(offer?.price || offer?.priceSpecification?.price),
          images: [entry.image].flat().map((image) => normalizedImageUrl(typeof image === "string" ? image : image?.url)).filter(Boolean) };
      }
    }
    return { name: "", description: "", price: "", images: [] };
  };
  const pageProduct = () => {
    const canonical = document.querySelector('link[rel="canonical"]')?.href || location.href;
    const ids = idsFromUrl(canonical);
    const matching = [...state.products.values()].find((item) => ids.product_id && item.product_id === ids.product_id
      && (!ids.shop_id || item.shop_id === ids.shop_id));
    const structured = structuredProduct(canonical);
    const metaImage = normalizedImageUrl(document.querySelector('meta[property="og:image"]')?.content || "");
    const images = [...new Set([metaImage, ...structured.images, ...productImages(document), ...(matching?.images || [])].filter(Boolean))].slice(0, 10);
    const title = pickText(document, ["h1", '[class*="product-name"]', '[data-testid*="product"] h1', 'meta[property="og:title"]']) || structured.name || matching?.product_name || clean(document.title).replace(/\s*\|\s*Shopee.*$/i, "");
    const description = (pickText(document, ['[data-sqe="product-detail"]', '[data-testid="product-description"]',
      '[class*="product-description"]']) || structured.description || matching?.description ||
      pickText(document, ['meta[property="og:description"]', 'meta[name="description"]'])).slice(0, 4000);
    return { ...matching, ...ids, product_name: title, price: structured.price || pickText(document, ['meta[property="product:price:amount"]', '[data-sqe="price"]', '[class*="price"]']) || matching?.price || "",
      commission: pickText(document, ['[class*="commission"]']) || matching?.commission || "", description,
      product_url: canonical, affiliate_url: location.href, images, captured_at: new Date().toISOString() };
  };

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type === "SCAN_PAGE") sendResponse({ ok: true, data: { page_supported: location.hostname.endsWith("shopee.co.th"), login_required: false, join_button_found: Boolean(findJoinButton()), product_count: state.products.size, product: pageProduct() } });
    if (message?.type === "CLICK_JOIN") {
      const button = findJoinButton();
      if (!button) sendResponse({ ok: false, error: "ไม่พบปุ่มเข้าร่วมเลย" });
      else { button.click(); sendResponse({ ok: true }); }
    }
  });
})();
