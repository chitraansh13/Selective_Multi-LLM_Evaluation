const API_URL = "http://127.0.0.1:8000/query";

const queryInput = document.getElementById("queryInput");
const submitButton = document.getElementById("submitButton");
const loadingState = document.getElementById("loadingState");
const resultCard = document.getElementById("resultCard");
const errorCard = document.getElementById("errorCard");

const queryValue = document.getElementById("queryValue");
const answerValue = document.getElementById("answerValue");
const modelsUsed = document.getElementById("modelsUsed");
const latencyValue = document.getElementById("latencyValue");
const stageValue = document.getElementById("stageValue");
const complexityBadge = document.getElementById("complexityBadge");
const modelsList = document.getElementById("modelsList");
const scoresList = document.getElementById("scoresList");
const reasoningList = document.getElementById("reasoningList");
const bestModelValue = document.getElementById("bestModelValue");

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.innerText = isLoading ? "Processing..." : "Submit";
  loadingState.classList.toggle("hidden", !isLoading);
}

function clearOutput() {
  resultCard.classList.add("hidden");
  resultCard.classList.remove("fade-in");
  queryValue.textContent = "";
  answerValue.innerHTML = "";
  modelsUsed.textContent = "0";
  latencyValue.textContent = "-";
  stageValue.textContent = "-";
  bestModelValue.textContent = "-";
  modelsList.innerHTML = "";
  scoresList.innerHTML = "";
  reasoningList.innerHTML = "";
  complexityBadge.textContent = "-";
  complexityBadge.className = "badge";
}

function showError(message) {
  errorCard.textContent = message;
  errorCard.classList.remove("hidden");
}

function clearError() {
  errorCard.textContent = "";
  errorCard.classList.add("hidden");
}

function formatLatency(latency) {
  if (!latency || typeof latency !== "object") {
    return "-";
  }

  const total = latency.total ?? latency.generation;
  if (typeof total !== "number") {
    return "-";
  }

  return `${total.toFixed(3)}s`;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatAnswer(text) {
  return escapeHtml(text)
    .replace(/### (.*)/g, "<h3>$1</h3>")
    .replace(/- (.*)/g, "<li>$1</li>")
    .replace(/\n/g, "<br>");
}

function renderModels(responseMap) {
  const names = Object.keys(responseMap || {});
  modelsList.innerHTML = "";

  names.forEach((name) => {
    const item = document.createElement("li");
    item.textContent = name;
    modelsList.appendChild(item);
  });

  modelsUsed.textContent = String(names.length);
}

function renderScores(scores, bestModel) {
  scoresList.innerHTML = "";
  reasoningList.innerHTML = "";

  Object.entries(scores || {}).forEach(([model, details]) => {
    const scoreCard = document.createElement("div");
    scoreCard.className = `score-item${model === bestModel ? " best" : ""}`;
    scoreCard.innerHTML = `
      <div class="score-row">
        <span class="score-model">${model}</span>
        <span class="score-badge">${details.score ?? 0}/10</span>
      </div>
    `;
    scoresList.appendChild(scoreCard);

    const reasonCard = document.createElement("div");
    reasonCard.className = `reason-item${model === bestModel ? " best" : ""}`;
    reasonCard.innerHTML = `
      <div class="score-row">
        <span class="score-model">${model}</span>
        <span class="score-badge">${details.score ?? 0}/10</span>
      </div>
      <p>${details.reason || "No reasoning available."}</p>
    `;
    reasoningList.appendChild(reasonCard);
  });
}

function renderResult(payload) {
  const data = payload.data || {};
  const complexity = data.complexity?.label || "unknown";
  const finalAnswer =
    data.final_answer ||
    Object.values(data.responses || {})[0] ||
    "No answer returned.";
  const bestModel = data.best_model || "Not selected";

  queryValue.textContent = data.query || "-";
  answerValue.innerHTML = `
    <div class="answer-block">
      ${formatAnswer(finalAnswer)}
    </div>
  `;
  stageValue.textContent = data.stage || "-";
  latencyValue.textContent = formatLatency(data.latency);
  complexityBadge.textContent = complexity;
  complexityBadge.className = `badge ${complexity}`;
  bestModelValue.textContent = `Best Model: ${bestModel}`;

  renderModels(data.responses);
  renderScores(data.scores, data.best_model);

  resultCard.classList.remove("hidden");
  resultCard.classList.add("fade-in");
}

async function submitQuery() {
  const query = queryInput.value.trim();
  if (!query) {
    showError("Please enter a query before submitting.");
    return;
  }

  clearError();
  clearOutput();
  setLoading(true);

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      throw new Error("Server error");
    }

    const result = await response.json();
    console.log("API Response:", result);

    if (!result.success) {
      throw new Error(result.error || "Unknown server error");
    }

    renderResult(result);
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "An unexpected error occurred while contacting the API.";
    showError(`Unable to get a response from SMERF. ${message}`);
    console.error("Frontend request failed:", error);
  } finally {
    setLoading(false);
  }
}

submitButton.addEventListener("click", submitQuery);

queryInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    submitQuery();
  }
});
