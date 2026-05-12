const form = document.querySelector("#job-form");
const submitButton = document.querySelector("#submit-button");
const statusPill = document.querySelector("#status-pill");
const log = document.querySelector("#log");
const result = document.querySelector("#result");
const downloadedCount = document.querySelector("#downloaded-count");
const failedCount = document.querySelector("#failed-count");
const qualityCount = document.querySelector("#quality-count");

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
      renderResult(state);
    }
  };
  events.onerror = () => {
    appendLog("事件连接中断，改用状态轮询。");
    events.close();
    submitButton.disabled = false;
  };
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  log.textContent = "正在提交任务。";
  result.textContent = "";
  downloadedCount.textContent = "0";
  failedCount.textContent = "0";
  qualityCount.textContent = "0";
  setStatus("running");

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "创建任务失败。");
    }
    appendLog(`任务已创建：${payload.job_id}`);
    if (payload.topic) {
      appendLog(`检索主题：${payload.topic}`);
    }
    watchEvents(payload.job_id);
  } catch (error) {
    setStatus("failed", error.message);
    submitButton.disabled = false;
  }
});

fetch("/api/config")
  .then((response) => response.json())
  .then((config) => {
    const outputInput = form.querySelector("input[name='output_dir']");
    outputInput.placeholder = `默认：${config.default_output_dir}`;
  })
  .catch(() => {});

