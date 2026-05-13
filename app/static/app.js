const form = document.querySelector("#job-form");
const planButton = document.querySelector("#plan-button");
const submitButton = document.querySelector("#submit-button");
const statusPill = document.querySelector("#status-pill");
const log = document.querySelector("#log");
const result = document.querySelector("#result");
const downloadedCount = document.querySelector("#downloaded-count");
const failedCount = document.querySelector("#failed-count");
const qualityCount = document.querySelector("#quality-count");
const planPanel = document.querySelector("#plan-panel");
const planConfidence = document.querySelector("#plan-confidence");
const planSummary = document.querySelector("#plan-summary");
const queryOptions = document.querySelector("#query-options");
const finalQueryInput = form.querySelector("textarea[name='final_query']");
const configBanner = document.querySelector("#config-banner");

function appendLog(message) {
  const timestamp = new Date().toLocaleTimeString();
  log.textContent += `\n[${timestamp}] ${message}`;
  log.scrollTop = log.scrollHeight;
}

function setStatus(status, message) {
  statusPill.textContent = status;
  statusPill.className = `status-pill ${status}`;
  if (message) {
    appendLog(message);
  }
}

function renderResult(payload) {
  if (!payload || !payload.result) {
    return;
  }
  const data = payload.result;
  downloadedCount.textContent = payload.downloaded_count ?? data.downloaded_count ?? 0;
  failedCount.textContent = payload.failed_count ?? data.failed_count ?? 0;
  qualityCount.textContent = payload.high_quality_count ?? data.high_quality_count ?? 0;
  result.innerHTML = `
    <div>PDF 目录：<code>${data.paper_dir || ""}</code></div>
    <div>高质量目录：<code>${data.high_quality_dir || ""}</code></div>
    <div>报告目录：<code>${data.reports_dir || ""}</code></div>
  `;
}

async function pollJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`);
  const data = await response.json();
  downloadedCount.textContent = data.downloaded_count ?? 0;
  failedCount.textContent = data.failed_count ?? 0;
  qualityCount.textContent = data.high_quality_count ?? 0;
  renderResult(data);
  return data;
}

function watchEvents(jobId) {
  const events = new EventSource(`/api/jobs/${jobId}/events`);
  events.onmessage = async (event) => {
    const payload = JSON.parse(event.data);
    setStatus(payload.status, payload.message);
    const state = await pollJob(jobId);
    if (payload.status === "completed" || payload.status === "failed") {
      events.close();
      submitButton.disabled = false;
      planButton.disabled = false;
      renderResult(state);
    }
  };
  events.onerror = () => {
    appendLog("事件连接中断，改用状态轮询。");
    events.close();
    submitButton.disabled = false;
    planButton.disabled = false;
  };
}

function renderSearchPlan(plan) {
  planPanel.classList.remove("hidden");
  planConfidence.textContent = `置信度 ${Number(plan.confidence || 0).toFixed(2)}`;
  finalQueryInput.value = plan.recommended_query || "";
  const synonyms = plan.synonyms || {};
  const synonymHtml = Object.keys(synonyms).length
    ? Object.entries(synonyms)
        .map(([term, values]) => `<div>${escapeHtml(term)}：${escapeHtml(values.join(", "))}</div>`)
        .join("")
    : "<div>暂无同义词建议</div>";
  planSummary.innerHTML = `
    <div>领域：<strong>${escapeHtml(plan.field || "未指定")}</strong></div>
    <div>核心关键词：${escapeHtml((plan.core_terms || []).join(", ") || "未生成")}</div>
    <div>${synonymHtml}</div>
    <div>${escapeHtml(plan.notes || "")}</div>
  `;
  queryOptions.innerHTML = "";
  (plan.query_options || []).forEach((option, index) => {
    const item = document.createElement("div");
    item.className = "query-option";
    item.innerHTML = `
      <label>
        <input type="radio" name="query_option" value="${index}" ${index === 0 ? "checked" : ""} />
        <span><strong>${escapeHtml(option.label || `查询 ${index + 1}`)}</strong></span>
      </label>
      <code>${escapeHtml(option.query || "")}</code>
      <div>${escapeHtml(option.reason || "")}</div>
    `;
    item.querySelector("input").addEventListener("change", () => {
      finalQueryInput.value = option.query || "";
    });
    queryOptions.appendChild(item);
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

planButton.addEventListener("click", async () => {
  planButton.disabled = true;
  submitButton.disabled = true;
  setStatus("running", "正在生成检索方案。");
  try {
    const response = await fetch("/api/search-plan", {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "生成检索方案失败。");
    }
    renderSearchPlan(payload);
    appendLog("检索方案已生成，请确认最终查询后开始下载。");
    setStatus("completed");
  } catch (error) {
    setStatus("failed", error.message);
  } finally {
    planButton.disabled = false;
    submitButton.disabled = false;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  planButton.disabled = true;
  log.textContent = "正在提交任务。";
  result.textContent = "";
  downloadedCount.textContent = "0";
  failedCount.textContent = "0";
  qualityCount.textContent = "0";
  setStatus("running");

  try {
    const formData = new FormData(form);
    if (!formData.get("final_query")) {
      formData.set("final_query", formData.get("topic") || "");
    }
    const response = await fetch("/api/jobs", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "创建任务失败。");
    }
    appendLog(`任务已创建：${payload.job_id}`);
    if (payload.topic) {
      appendLog(`最终查询：${payload.topic}`);
    }
    if (payload.note) {
      appendLog(payload.note);
    }
    watchEvents(payload.job_id);
  } catch (error) {
    setStatus("failed", error.message);
    submitButton.disabled = false;
    planButton.disabled = false;
  }
});

fetch("/api/config")
  .then((response) => response.json())
  .then((config) => {
    const outputInput = form.querySelector("input[name='output_dir']");
    outputInput.placeholder = `默认：${config.default_output_dir}`;
    if (config.deepseek_configured) {
      configBanner.textContent = `DeepSeek 已配置：${config.deepseek_model}`;
      configBanner.className = "config-banner";
    } else {
      configBanner.textContent = "DeepSeek API Key 未配置：将使用本地兜底方案，中文专业词翻译和同义词效果会受限。";
      configBanner.className = "config-banner warning";
    }
  })
  .catch(() => {});
