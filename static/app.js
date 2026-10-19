const state = { items: [], category: "全部", dealType: "全部", sort: "drop" };
const grid = document.querySelector("#dealGrid");
const template = document.querySelector("#dealTemplate");
const notice = document.querySelector("#notice");
const empty = document.querySelector("#emptyState");
const scanButton = document.querySelector("#scanButton");
const settingsForm = document.querySelector("#settingsForm");

function money(value) { return Number(value).toFixed(2).replace(/\.00$/, ""); }
function formatTime(value) {
  if (!value) return "尚未";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "尚未" : date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}
function relativeTime(value) {
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  if (!Number.isFinite(seconds)) return "校验时间未知";
  if (seconds < 90) return "刚刚校验";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟前校验`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时前校验`;
  return `${Math.floor(seconds / 86400)}天前校验`;
}
function showNotice(message) {
  notice.textContent = message;
  notice.hidden = !message;
}

function renderCapabilities(capabilities) {
  const labels = {
    jingfen: "京粉精选", material: "商品素材", activity: "公开活动",
    bigfield: "商品规格", rank: "排行榜", promotion_link: "推广转链",
    goods_query: "全站商品搜索", coupon_query: "优惠券校验",
    promotion_intelligence: "官方优惠线报", combination_query: "跨商品凑单",
    account_checkout: "账号/支付专享价",
  };
  const statuses = {
    enabled: ["已接入", "ok"], available: ["权限可用", "ok"],
    needs_parameters: ["待确认榜单参数", "pending"], needs_site_id: ["缺媒体ID", "pending"],
    needs_position_id: ["缺推广位ID", "pending"],
    social_media_unsupported: ["导购媒体不适用", "pending"],
    permission_missing: ["待京东授权", "missing"], not_public_api: ["无公开接口", "missing"],
  };
  const grid = document.querySelector("#capabilityGrid");
  grid.replaceChildren(...Object.entries(capabilities || {}).map(([key, value]) => {
    const item = document.createElement("div");
    const [text, className] = statuses[value] || [value, "pending"];
    const label = document.createElement("span"); label.textContent = labels[key] || key;
    const badge = document.createElement("b"); badge.className = className; badge.textContent = text;
    item.append(label, badge);
    return item;
  }));
}

function renderCategories() {
  const categories = ["全部", ...new Set(state.items.map(item => item.category))];
  const box = document.querySelector("#categories");
  box.replaceChildren(...categories.map(category => {
    const button = document.createElement("button");
    button.className = `category-chip${state.category === category ? " active" : ""}`;
    button.textContent = category;
    button.onclick = () => { state.category = category; renderCategories(); renderDeals(); };
    return button;
  }));
}

function renderDealTypes() {
  const types = [
    ["全部", "全部"], ["historical_drop", "历史总价下降"],
    ["unit_drop", "历史单位价下降"], ["new_public_offer", "公开优惠"],
  ];
  const box = document.querySelector("#dealTypes");
  box.replaceChildren(...types.map(([value, label]) => {
    const count = value === "全部" ? state.items.length : state.items.filter(item => item.deal_kind === value).length;
    const button = document.createElement("button");
    button.className = `category-chip type-chip${state.dealType === value ? " active" : ""}`;
    button.textContent = `${label} ${count}`;
    button.onclick = () => { state.dealType = value; renderDealTypes(); renderDeals(); };
    return button;
  }));
}

function renderDeals() {
  let items = state.items.filter(item =>
    (state.category === "全部" || item.category === state.category) &&
    (state.dealType === "全部" || item.deal_kind === state.dealType)
  );
  const sorters = {
    drop: (a, b) => b.drop_percent - a.drop_percent,
    price: (a, b) => a.current_price - b.current_price,
    unit: (a, b) => (a.unit_price ?? Infinity) - (b.unit_price ?? Infinity),
  };
  items = [...items].sort(sorters[state.sort]);
  grid.replaceChildren();
  for (const item of items) {
    const card = template.content.cloneNode(true);
    card.querySelector(".drop-badge").textContent = `↓ ${money(item.drop_percent)}%`;
    const kindLabels = {
      historical_drop: "真实历史降价", unit_drop: "同规格单位价下降",
      new_public_offer: "公开优惠价", legacy: "待重新校验",
    };
    card.querySelector(".deal-kind-badge").textContent = kindLabels[item.deal_kind] || "价格发现";
    card.querySelector(".category").textContent = item.category;
    card.querySelector(".source").textContent = item.source;
    card.querySelector(".product-name").textContent = item.name;
    card.querySelector(".offer-text").textContent = item.reason || item.offer_text;
    const confidenceLabels = { high: "高可信", medium: "公开券·需领取", conditional: "有条件优惠" };
    const confidence = card.querySelector(".confidence");
    confidence.textContent = confidenceLabels[item.confidence] || "待核验";
    confidence.classList.add(item.confidence || "conditional");
    card.querySelector(".verified-at").textContent = relativeTime(item.captured_at);
    card.querySelector(".current-price").textContent = money(item.current_price);
    const priceKind = card.querySelector(".price-kind");
    if (item.price_type === "coupon_estimate") {
      priceKind.textContent = "京东接口预估券后价";
    } else if (item.price_type === "promotion_estimate") {
      priceKind.textContent = "京东接口预估优惠价";
    } else {
      priceKind.textContent = "当前价格";
    }
    const referenceWrap = card.querySelector(".reference-wrap");
    if (item.comparison_kind === "unit_price" && item.reference_unit_price) {
      referenceWrap.textContent = `历史单位价 ¥${money(item.reference_unit_price)}`;
    } else {
      card.querySelector(".reference-price").textContent = `¥${money(item.reference_price)}`;
    }
    card.querySelector(".pack-label").textContent = item.pack_label || "单件";
    card.querySelector(".unit-price").textContent = item.unit_price ? `${money(item.unit_price)} ${item.unit_label}` : "待计算";
    const link = card.querySelector(".view-link");
    link.href = item.product_url;
    const couponLink = card.querySelector(".coupon-link");
    if (item.coupon_url) {
      couponLink.href = item.coupon_url;
      couponLink.hidden = false;
      const discount = item.coupon_discount ? `${money(item.coupon_discount)}元` : "";
      couponLink.textContent = `先领${discount}券`;
      card.querySelector(".card-actions").classList.add("has-coupon");
    }
    const copy = card.querySelector(".copy-button");
    copy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(item.product_url);
        copy.textContent = "已复制";
        setTimeout(() => copy.textContent = "复制链接", 1300);
      } catch (_) {
        window.prompt("复制这个链接：", item.product_url);
      }
    };
    const image = card.querySelector(".product-image");
    const placeholder = card.querySelector(".image-placeholder");
    if (item.image_url) {
      image.src = item.image_url;
      image.alt = item.name;
      image.hidden = false;
      placeholder.hidden = true;
      image.onerror = () => { image.hidden = true; placeholder.hidden = false; };
    }
    grid.appendChild(card);
  }
  empty.hidden = items.length > 0;
  document.querySelector("#dealCount").textContent = state.items.length;
}

async function load() {
  try {
    const [dealResponse, statusResponse] = await Promise.all([fetch("/api/deals"), fetch("/api/status")]);
    const deals = await dealResponse.json();
    const status = await statusResponse.json();
    state.items = deals.items || [];
    document.querySelector("#trackedCount").textContent = status.tracked_count;
    document.querySelector("#lastScan").textContent = formatTime(status.last_scan);
    document.querySelector("#modeBadge").textContent = status.mode === "live" ? "京东实时数据" : "演示数据模式";
    document.querySelector("#thresholdInput").value = status.threshold_percent;
    document.querySelector("#intervalInput").value = status.interval_minutes;
    if (status.public_read_only) {
      document.querySelector("#scanButton").hidden = true;
      document.querySelector("#settingsForm").hidden = true;
    }
    document.querySelector("#autoSummary").textContent = `后台每 ${status.interval_minutes} 分钟扫描 13 个京粉频道＋${status.material_channel_count} 个素材频道；本轮第 ${status.last_scan_page}/${status.page_cycle} 页共 ${status.last_scan_count} 件、新增 ${status.last_new_count} 件。真实历史价、同规格单位价或当前公开优惠达到 ${money(status.threshold_percent)}% 时分类展示。`;
    const warning = status.last_error || status.source_warnings || status.activity_error;
    showNotice(warning ? `部分数据源提示：${warning}` : (status.mode === "demo" ? "当前为演示数据。配置本机 .env 后可切换到京东实时接口。" : ""));
    renderCapabilities(status.capabilities);
    renderCategories();
    renderDealTypes();
    renderDeals();
  } catch (error) {
    showNotice(`无法读取监控数据：${error.message}`);
  }
}

scanButton.onclick = async () => {
  scanButton.disabled = true;
  scanButton.textContent = "扫描中…";
  try {
    const response = await fetch("/api/scan", { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "扫描失败");
    await load();
  } catch (error) {
    showNotice(error.message);
  } finally {
    scanButton.disabled = false;
    scanButton.textContent = "手动补扫";
  }
};
settingsForm.onsubmit = async event => {
  event.preventDefault();
  const button = document.querySelector("#saveSettings");
  button.disabled = true;
  button.textContent = "正在保存并扫描…";
  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        threshold_percent: Number(document.querySelector("#thresholdInput").value),
        interval_minutes: Number(document.querySelector("#intervalInput").value),
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "保存失败");
    showNotice(`规则已保存：每 ${result.interval_minutes} 分钟自动扫描，降幅达到 ${money(result.threshold_percent)}% 时展示。`);
    await load();
  } catch (error) {
    showNotice(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "保存并立即生效";
  }
};
document.querySelector("#sortSelect").onchange = event => { state.sort = event.target.value; renderDeals(); };
load();
setInterval(load, 60 * 1000);

