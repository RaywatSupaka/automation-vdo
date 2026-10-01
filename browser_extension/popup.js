const BRIDGE = "http://127.0.0.1:8765";
let scanned = null;
let flowPackage = null;
const $ = (id) => document.getElementById(id);
// No membership/Token authorization in the Extension. The connection card
// below distinguishes engine availability from actual local pairing. Desktop
// Login is independent; the popup never receives the session capability.

function isFlowUrl(value) {
  return /^(?:https:\/\/flow\.google\.com(?:\/|$)|https:\/\/labs\.google\/(?:fx|flow)(?:\/|$))/i
    .test(String(value || ""));
}

function setStatus(dot, label, ok, text) {
  $(dot).className = `dot ${ok ? "ok" : "bad"}`;
  $(label).textContent = text;
}

function showFlowPackage(pkg) {
  flowPackage = pkg;
  $("flowCard").classList.remove("hidden");
  $("flowJob").textContent = `${pkg.job_id} • ${pkg.product_name || "สินค้า"}`;
  $("flowReview").textContent = pkg.ai_review_status === "approved"
    ? "AI ผ่านการอนุมัติแล้ว"
    : "กรุณาตรวจและอนุมัติ AI ในโปรแกรมก่อนใช้จริง";
  $("openFlowButton").classList.remove("hidden");
  $("copyPromptButton").classList.toggle("hidden", !pkg.video_prompt);
  $("downloadImageButton").classList.toggle("hidden", !pkg.image_urls?.length);
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function scanTab(tab) {
  try {
    return await chrome.tabs.sendMessage(tab.id, { type: "SCAN_PAGE" });
  } catch {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    return await chrome.tabs.sendMessage(tab.id, { type: "SCAN_PAGE" });
  }
}

async function loadFlowPackage() {
  const result = await chrome.runtime.sendMessage({ type: "GET_FLOW_PACKAGE" });
  if (result?.ok && result.package) showFlowPackage(result.package);
  return result;
}

async function refresh() {
  $("message").textContent = "";
  try {
    const response = await chrome.runtime.sendMessage({type:'GET_CONNECTION_STATUS'});
    const connection=response?.connection;
    if(!response?.ok || !connection?.reachable)throw new Error();
    const compatible=connection.paired && !connection.updateRequired;
    const label=connection.updateRequired
      ? `ต้องอัปเดต Extension ${connection.currentVersion} → ${connection.requiredVersion} แล้วโหลดซ้ำที่ตัวเดิม`
      : connection.paired ? 'เชื่อมต่อโปรแกรม Windows แล้ว'
      : 'พบโปรแกรม แต่ยังไม่จับคู่ Extension • ตรวจโฟลเดอร์และกดโหลดซ้ำ';
    setStatus("bridgeDot", "bridgeStatus", compatible, label);
  } catch {
    setStatus("bridgeDot", "bridgeStatus", false, "กรุณาเปิดโปรแกรม Windows");
  }

  const tab = await activeTab();
  const isShopee = tab?.url?.startsWith("https://affiliate.shopee.co.th/");
  const isChatGPT = tab?.url?.startsWith("https://chatgpt.com/");
  const isGemini = tab?.url?.startsWith("https://gemini.google.com/");
  const isFlow = isFlowUrl(tab?.url);
  $("importButton").classList.toggle("hidden", !isShopee);
  $("joinButton").classList.add("hidden");

  try {
    if (isShopee) {
      const result = await scanTab(tab);
      scanned = result.data;
      if (scanned.login_required) setStatus("pageDot", "pageStatus", false, "กรุณา Login Shopee Affiliate ก่อน");
      else setStatus("pageDot", "pageStatus", true, "เชื่อมต่อหน้า Shopee Affiliate แล้ว");
      const product = scanned.product;
      if (product.product_name) {
        $("productCard").classList.remove("hidden");
        $("productName").textContent = product.product_name;
        $("productMeta").textContent = [product.price, product.commission].filter(Boolean).join(" • ") || "พร้อมนำเข้า";
        if (product.images[0]) $("productImage").src = product.images[0];
        $("importButton").disabled = scanned.login_required;
      } else {
        $("productCard").classList.add("hidden");
        $("importButton").disabled = true;
        $("message").textContent = "ยังไม่พบข้อมูลสินค้าในหน้านี้ ให้เปิดหน้ารายการหรือรายละเอียดสินค้า";
      }
      $("joinButton").classList.toggle("hidden", !scanned.join_button_found);
    } else if (isChatGPT) {
      setStatus("pageDot", "pageStatus", true, "เชื่อมต่อหน้า ChatGPT Web แล้ว");
      $("productCard").classList.add("hidden");
    } else if (isGemini) {
      setStatus("pageDot", "pageStatus", true, "เชื่อมต่อหน้า Gemini Web แล้ว");
      $("productCard").classList.add("hidden");
    } else if (isFlow) {
      setStatus("pageDot", "pageStatus", true, "เชื่อมต่อหน้า Google Flow แล้ว");
      $("productCard").classList.add("hidden");
    } else {
      setStatus("pageDot", "pageStatus", false, "เปิดหน้า Shopee, ChatGPT, Gemini หรือ Google Flow");
      $("importButton").disabled = true;
    }
    const flowResult = await loadFlowPackage();
    if (!flowResult?.ok && isFlow) $("message").textContent = flowResult?.error || "ยังไม่ได้เลือก Job";
  } catch (error) {
    setStatus("pageDot", "pageStatus", false, error.message || "อ่านหน้านี้ไม่ได้");
    $("importButton").disabled = true;
  }
}

$("importButton").addEventListener("click", async () => {
  if (!scanned?.product) return;
  $("importButton").disabled = true;
  $("message").textContent = "กำลังบันทึกสินค้าและรูป...";
  try {
    // Keep the session capability inside the background service worker. Popup
    // pages never receive or persist the Local Bridge token directly.
    const response = await chrome.runtime.sendMessage({
      type: "IMPORT_PRODUCTS",
      products: [scanned.product]
    });
    const result = response?.results?.[0];
    if (!response?.ok || !result?.ok || !result?.job?.id) {
      throw new Error(result?.error || response?.error || "นำเข้าสินค้าไม่สำเร็จ");
    }
    await chrome.runtime.sendMessage({ type: "SET_ACTIVE_JOB", jobId: result.job.id });
    $("message").textContent = result.created ? `สร้าง ${result.job.id} แล้ว` : `พบสินค้านี้อยู่แล้ว: ${result.job.id}`;
    await loadFlowPackage();
  } catch (error) {
    $("message").textContent = `นำเข้าไม่สำเร็จ: ${error.message}`;
  } finally {
    $("importButton").disabled = false;
  }
});

$("openFlowButton").addEventListener("click", async () => {
  const result = await chrome.runtime.sendMessage({ type: "OPEN_FLOW" });
  if (!result?.ok) $("message").textContent = result?.error || "เปิด Google Flow ไม่สำเร็จ";
});

$("copyPromptButton").addEventListener("click", async () => {
  if (!flowPackage?.video_prompt) return;
  await navigator.clipboard.writeText(flowPackage.video_prompt);
  $("message").textContent = "คัดลอกพรอมต์ Google Flow แล้ว";
});

$("downloadImageButton").addEventListener("click", async () => {
  if (!flowPackage?.image_urls?.[0]) return;
  const result = await chrome.runtime.sendMessage({
    type: "DOWNLOAD_FLOW_IMAGE",
    url: flowPackage.image_urls[0],
    jobId: flowPackage.job_id
  });
  $("message").textContent = result?.ok ? "ดาวน์โหลดรูปไว้ใน Downloads/SmartPost แล้ว" : (result?.error || "ดาวน์โหลดไม่สำเร็จ");
});

$("joinButton").addEventListener("click", async () => {
  if (!confirm("ยืนยันกด “เข้าร่วมเลย” บนหน้าปัจจุบัน?")) return;
  const tab = await activeTab();
  const result = await chrome.tabs.sendMessage(tab.id, { type: "CLICK_JOIN" });
  $("message").textContent = result.ok ? "กดแล้ว กรุณาตรวจผลบนหน้าเว็บ" : result.error;
});

$("refreshButton").addEventListener("click", refresh);
refresh();
