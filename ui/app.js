const el = (id) => document.getElementById(id);

const stateEls = {
  score: el("score-val"),
  step: el("step-val"),
  discovered: el("discovered-val"),
  verification: el("verification-val"),
  health: el("health-pill"),
  resources: el("resource-cards"),
  issues: el("issues-wrap"),
  logs: el("log-wrap"),
  breakdown: el("breakdown-wrap"),
  demoResults: el("demo-results-list"),
  timeline: el("timeline-track"),
  status: el("what-happened"),
  autoProgressText: el("auto-progress-text"),
  autoProgressFill: el("auto-progress-fill"),
  workflowStart: el("wf-start"),
  workflowScan: el("wf-scan"),
  workflowFix: el("wf-fix"),
  workflowVerify: el("wf-verify"),
  workflowDone: el("wf-done"),
  workflowCaption: el("workflow-caption"),
};

let currentState = null;
let demoRunning = false;
let autoRunning = false;
let timelineEvents = [];
let availableTaskIds = [];
let availableActions = [];
let availableResourceFields = [];
let taskResetTimer = null;

function setHealth(ok, text) {
  stateEls.health.textContent = text;
  stateEls.health.style.color = ok ? "#59efb0" : "#ff7f8e";
}

function setStatus(text) {
  if (stateEls.status) {
    stateEls.status.textContent = `Status: ${text}`;
  }
}

function setAutoProgress(completed, total) {
  if (stateEls.autoProgressText) {
    stateEls.autoProgressText.textContent = `${completed} / ${total}`;
  }
  if (stateEls.autoProgressFill) {
    const safeTotal = Math.max(Number(total || 0), 1);
    const percent = Math.min(100, Math.round((Number(completed || 0) / safeTotal) * 100));
    stateEls.autoProgressFill.style.width = `${percent}%`;
  }
}

function setWorkflowState(stage, caption) {
  const stages = [
    [stateEls.workflowStart, "done"],
    [stateEls.workflowScan, "done"],
    [stateEls.workflowFix, "done"],
    [stateEls.workflowVerify, "done"],
    [stateEls.workflowDone, "done"],
  ];

  for (const [node] of stages) {
    if (node) {
      node.classList.remove("active", "done");
    }
  }

  const apply = (node, cls) => {
    if (node) {
      node.classList.add(cls);
    }
  };

  if (stage === "start") {
    apply(stateEls.workflowStart, "active");
  } else if (stage === "scan") {
    apply(stateEls.workflowStart, "done");
    apply(stateEls.workflowScan, "active");
  } else if (stage === "fix") {
    apply(stateEls.workflowStart, "done");
    apply(stateEls.workflowScan, "done");
    apply(stateEls.workflowFix, "active");
  } else if (stage === "verify") {
    apply(stateEls.workflowStart, "done");
    apply(stateEls.workflowScan, "done");
    apply(stateEls.workflowFix, "done");
    apply(stateEls.workflowVerify, "active");
  } else if (stage === "done") {
    apply(stateEls.workflowStart, "done");
    apply(stateEls.workflowScan, "done");
    apply(stateEls.workflowFix, "done");
    apply(stateEls.workflowVerify, "done");
    apply(stateEls.workflowDone, "active");
  }

  if (stateEls.workflowCaption && caption) {
    stateEls.workflowCaption.textContent = caption;
  }
}

function updateWorkflowView(state) {
  if (!state) {
    setWorkflowState("start", "Select a task to see the workflow.");
    return;
  }

  if (state.done) {
    setWorkflowState("done", `Completed ${state.task_id || state.task?.task_id || "task"}. The environment is fully remediated.`);
    return;
  }

  if (!state.discovered) {
    setWorkflowState("scan", "Step 1: start the task, then scan to discover issues.");
    return;
  }

  if (state.pending_verification) {
    setWorkflowState("verify", "Step 4: verification scan is required after fixes.");
    return;
  }

  const openIssues = (state.issues || []).filter((issue) => !issue.fixed);
  if (openIssues.length === 0) {
    setWorkflowState("done", "All visible issues are fixed. The task is ready to complete.");
    return;
  }

  setWorkflowState("fix", "Step 3: apply the recommended fixes for the remaining issues.");
}

function getTaskWorkflowCaption(state) {
  if (!state) {
    return "Select a task to see its workflow.";
  }

  const taskLabel = String(state.task?.title || state.task_id || state.task?.task_id || "Selected task");
  if (state.done) {
    return `${taskLabel}: completed successfully.`;
  }
  if (!state.discovered) {
    return `${taskLabel}: start the task, then scan to discover issues.`;
  }

  const openCount = Array.isArray(state.issues)
    ? state.issues.filter((issue) => !issue.fixed).length
    : 0;
  return `${taskLabel}: ${openCount} issue${openCount === 1 ? "" : "s"} remaining.`;
}

function getTaskSelectOptions() {
  const select = el("task-select");
  if (!select) {
    return [];
  }
  return Array.from(select.options).map((opt) => opt.value).filter(Boolean);
}

function populateTaskSelect(taskIds) {
  const select = el("task-select");
  if (!select || !Array.isArray(taskIds) || taskIds.length === 0) {
    return;
  }

  const previous = select.value;
  select.innerHTML = "";
  for (const taskId of taskIds) {
    const option = document.createElement("option");
    option.value = taskId;
    option.textContent = taskId;
    select.appendChild(option);
  }

  select.value = taskIds.includes(previous) ? previous : taskIds[0];
  availableTaskIds = [...taskIds];
}

function getActionSelectOptions() {
  const select = el("action-select");
  if (!select) {
    return [];
  }
  return Array.from(select.options).map((opt) => opt.value).filter(Boolean);
}

function populateActionSelect(actions) {
  const select = el("action-select");
  if (!select || !Array.isArray(actions) || actions.length === 0) {
    return;
  }

  const previous = select.value;
  select.innerHTML = "";
  for (const action of actions) {
    const option = document.createElement("option");
    option.value = action;
    option.textContent = action;
    select.appendChild(option);
  }

  select.value = actions.includes(previous) ? previous : actions[0];
  availableActions = [...actions];
}

function populateResourceFields(fields) {
  if (!Array.isArray(fields) || fields.length === 0) {
    return;
  }
  availableResourceFields = fields.filter((field) => field && typeof field.key === "string");
}

function parseActionTypesFromSchema(schema) {
  if (!schema || typeof schema !== "object") {
    return [];
  }

  const directEnum = schema?.action?.properties?.action_type?.enum;
  if (Array.isArray(directEnum) && directEnum.every((x) => typeof x === "string")) {
    return [...directEnum];
  }

  const actionTypeRef = schema?.action?.properties?.action_type?.$ref;
  if (typeof actionTypeRef === "string") {
    const defName = actionTypeRef.split("/").pop();
    const enumFromRef = defName ? schema?.action?.$defs?.[defName]?.enum : null;
    if (Array.isArray(enumFromRef) && enumFromRef.every((x) => typeof x === "string")) {
      return [...enumFromRef];
    }
  }

  const defs = schema?.action?.$defs;
  if (defs && typeof defs === "object") {
    for (const candidate of Object.values(defs)) {
      if (candidate && Array.isArray(candidate.enum) && candidate.enum.every((x) => typeof x === "string")) {
        return [...candidate.enum];
      }
    }
  }

  return [];
}

async function loadTaskCatalog() {
  try {
    const metadata = await api("/metadata");
    const tasks = Array.isArray(metadata?.tasks) ? metadata.tasks : [];
    if (tasks.length > 0) {
      populateTaskSelect(tasks);
    } else {
      availableTaskIds = getTaskSelectOptions();
    }
  } catch {
    availableTaskIds = getTaskSelectOptions();
  }
}

async function loadActionCatalog() {
  try {
    const schema = await api("/schema");
    const actions = parseActionTypesFromSchema(schema);
    if (actions.length > 0) {
      populateActionSelect(actions);
    } else {
      availableActions = getActionSelectOptions();
    }
  } catch {
    availableActions = getActionSelectOptions();
  }
}

async function loadResourceCatalog() {
  try {
    const schema = await api("/schema");
    const resourceProps = schema?.state?.$defs?.ResourceState?.properties;
    if (resourceProps && typeof resourceProps === "object") {
      const fields = Object.entries(resourceProps).map(([key, details]) => ({
        key,
        title: typeof details?.title === "string" && details.title.trim() ? details.title : pretty(key),
      }));
      populateResourceFields(fields);
    }
  } catch {
    availableResourceFields = [];
  }
}

function pretty(key) {
  return key.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function nowStamp() {
  const d = new Date();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

function renderTimeline() {
  stateEls.timeline.innerHTML = "";
  if (!timelineEvents.length) {
    stateEls.timeline.innerHTML = '<div class="timeline-item muted">Timeline appears as actions run.</div>';
    return;
  }

  for (const ev of timelineEvents) {
    const item = document.createElement("article");
    item.className = `timeline-item ${ev.level || ""}`;
    item.innerHTML = `
      <div class="timeline-top">
        <span class="badge">${ev.taskId}</span>
        <span class="timeline-time">${ev.time}</span>
      </div>
      <div class="timeline-action">${ev.action}</div>
      <div class="timeline-meta">
        <span class="timeline-chip">reward=${ev.reward}</span>
        <span class="timeline-chip">score=${ev.score}</span>
        <span class="timeline-chip">step=${ev.step}</span>
      </div>
      <div class="timeline-note">${ev.note}</div>
    `;
    stateEls.timeline.appendChild(item);
  }

  stateEls.timeline.scrollLeft = stateEls.timeline.scrollWidth;
}

function resetTimeline() {
  timelineEvents = [];
  renderTimeline();
}

function pushTimelineEvent(event) {
  timelineEvents.push(event);
  if (timelineEvents.length > 120) {
    timelineEvents = timelineEvents.slice(-120);
  }
  renderTimeline();
}

async function api(path, method = "GET", body = null) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `Request failed: ${res.status}`);
  }
  return res.json();
}

function renderState(payload) {
  const s = payload.state || payload;
  currentState = s;

  stateEls.score.textContent = Number(s.score ?? 0).toFixed(2);
  stateEls.step.textContent = String(s.step_count ?? 0);
  stateEls.discovered.textContent = s.discovered ? "yes" : "no";
  stateEls.verification.textContent = s.pending_verification ? "yes" : "no";

  const resources = s.resources || {};
  stateEls.resources.innerHTML = "";
  const resourceMap = availableResourceFields.length > 0
    ? availableResourceFields
    : Object.keys(resources).map((key) => ({ key, title: pretty(key) }));

  for (const { key, title } of resourceMap) {
    const ok = Boolean(resources[key]);
    const card = document.createElement("article");
    card.className = `resource-card ${ok ? "ok" : "bad"}`;
    card.innerHTML = `
      <div class="resource-title">${title}</div>
      <div class="resource-state">${ok ? "Secure" : "At Risk"}</div>
    `;
    stateEls.resources.appendChild(card);
  }

  stateEls.issues.innerHTML = "";
  const issues = s.discovered ? (s.issues || []) : [];
  if (!s.discovered || issues.length === 0) {
    stateEls.issues.innerHTML = '<div class="issue-item">No issues visible yet. Run scan_resources first.</div>';
  } else {
    for (const issue of issues) {
      const item = document.createElement("article");
      item.className = `issue-item ${issue.fixed ? "fixed" : "open"}`;
      item.innerHTML = `
        <div class="issue-top">
          <div class="issue-title">${issue.title}</div>
          <span class="badge ${issue.severity}">${issue.severity}</span>
        </div>
        <div class="resource-title">ID: ${issue.issue_id} | Resource: ${issue.resource_id}</div>
        <div class="resource-title">Required Action: ${issue.required_action}</div>
      `;
      stateEls.issues.appendChild(item);
    }
  }

  stateEls.logs.innerHTML = "";
  const logs = s.action_history || [];
  if (logs.length === 0) {
    stateEls.logs.innerHTML = '<div class="log-item"><small>No actions yet.</small></div>';
  } else {
    for (const log of logs.slice().reverse()) {
      const node = document.createElement("div");
      node.className = "log-item";
      const status = log.error ? `error: ${log.error}` : "ok";
      node.innerHTML = `
        <div><strong>Step ${log.step}</strong> - ${log.action_type}</div>
        <small>reward=${Number(log.reward).toFixed(2)} | ${status}</small>
      `;
      stateEls.logs.appendChild(node);
    }
  }

  const taskId = s.task_id || s.task?.task_id || "";
  if (!s.discovered) {
    setWorkflowState("scan", getTaskWorkflowCaption(s));
  } else if (s.done) {
    setWorkflowState("done", getTaskWorkflowCaption(s));
  } else if (s.pending_verification) {
    setWorkflowState("verify", getTaskWorkflowCaption(s));
  } else if ((s.issues || []).some((issue) => !issue.fixed)) {
    setWorkflowState("fix", getTaskWorkflowCaption(s));
  } else {
    setWorkflowState("done", getTaskWorkflowCaption(s));
  }
}

function renderBreakdown(details) {
  stateEls.breakdown.innerHTML = "";
  const entries = Object.entries(details || {});
  if (!entries.length) {
    stateEls.breakdown.innerHTML = '<div class="breakdown-item">Breakdown appears after a step.</div>';
    return;
  }

  for (const [key, raw] of entries) {
    const value = Math.max(0, Math.min(1, Number(raw) || 0));
    const row = document.createElement("div");
    row.className = "breakdown-item";
    row.innerHTML = `
      <div class="breakdown-label"><span>${pretty(key)}</span><span>${value.toFixed(2)}</span></div>
      <div class="breakdown-bar"><span style="width:${(value * 100).toFixed(0)}%"></span></div>
    `;
    stateEls.breakdown.appendChild(row);
  }
}

function chooseResourceForAction(actionType, state) {
  if (!state || !state.issues) {
    return "";
  }
  const issue = state.issues.find((x) => !x.fixed && x.required_action === actionType);
  return issue ? issue.resource_id : "";
}

async function refreshState() {
  try {
    const data = await api("/state");
    renderState(data);
    setHealth(true, "Live");
  } catch (err) {
    setHealth(false, "Offline");
    console.error(err);
  }
}

async function resetTask(clearTimeline = true) {
  const taskId = el("task-select").value;
  try {
    const data = await api("/reset", "POST", { task_id: taskId });
    renderState(data.state);
    renderBreakdown({});
    setAutoProgress(0, Number(data.state?.task?.max_steps || 0));
    setWorkflowState("scan", getTaskWorkflowCaption(data.state));
    if (clearTimeline) {
      resetTimeline();
    }
    pushTimelineEvent({
      taskId,
      time: nowStamp(),
      action: "reset",
      reward: "0.00",
      score: Number(data.state?.score || 0).toFixed(2),
      step: String(data.state?.step_count || 0),
      note: "Task reset and ready for actions.",
      level: "warn",
    });
    setStatus(`started ${taskId}. Click Next Best Step.`);
    setHealth(true, "Reset OK");
  } catch (err) {
    setHealth(false, "Reset Failed");
    alert(`Reset failed: ${err.message}`);
    throw err;
  }
}

async function applyStep() {
  const actionType = el("action-select").value;
  const autoResource = chooseResourceForAction(actionType, currentState);
  const providedResource = el("resource-input").value.trim();
  const targetResource = providedResource || autoResource || null;

  return applyAction(actionType, targetResource);
}

async function applyAction(actionType, targetResource) {
  const resolvedTarget = targetResource || chooseResourceForAction(actionType, currentState) || null;

  const payload = {
    action_type: actionType,
    target_resource: actionType === "scan_resources" || actionType === "noop" ? null : resolvedTarget,
    notes: "UI action",
  };

  try {
    const data = await api("/step", "POST", payload);
    const state = await api("/state");
    renderState(state);
    renderBreakdown(data.info?.score_breakdown || {});
    setAutoProgress(Number(state.step_count || 0), Number(state.task?.max_steps || 0));

    const hasError = Boolean(data.info?.last_action_error);
    pushTimelineEvent({
      taskId: state.task?.task_id || currentState?.task?.task_id || "unknown_task",
      time: nowStamp(),
      action: actionType,
      reward: Number(data.reward?.value || 0).toFixed(2),
      score: Number(state.score || 0).toFixed(2),
      step: String(state.step_count || 0),
      note: hasError
        ? `warning: ${data.info?.last_action_error}`
        : resolvedTarget
          ? `target=${resolvedTarget}`
          : "no target required",
      level: hasError ? "fail" : scoreLevel(Number(state.score || 0)),
    });

    if (hasError) {
      setStatus(`action warning: ${data.info?.last_action_error}`);
      setHealth(false, "Action warning");
    } else {
      if (state.done) {
        setStatus(`task completed with score ${Number(state.score || 0).toFixed(2)}.`);
        setWorkflowState("done", getTaskWorkflowCaption(state));
      } else {
        setStatus(`applied ${actionType}. score now ${Number(state.score || 0).toFixed(2)}.`);
        if (!state.discovered) {
          setWorkflowState("scan", getTaskWorkflowCaption(state));
        } else if (state.pending_verification) {
          setWorkflowState("verify", getTaskWorkflowCaption(state));
        } else {
          setWorkflowState("fix", getTaskWorkflowCaption(state));
        }
      }
      setHealth(true, "Step OK");
    }
  } catch (err) {
    setHealth(false, "Step Failed");
    alert(`Step failed: ${err.message}`);
    throw err;
  }
}

function getNextBestAction(state) {
  if (!state) {
    return ["scan_resources", null];
  }

  if (!state.discovered) {
    return ["scan_resources", null];
  }

  if (state.pending_verification) {
    return ["scan_resources", null];
  }

  const openIssues = (state.issues || []).filter((issue) => !issue.fixed);
  const byIssue = Object.fromEntries(openIssues.map((issue) => [issue.issue_id, issue]));

  if (byIssue.IAM_WEAK) {
    return ["update_iam_policy", byIssue.IAM_WEAK.resource_id];
  }
  if (byIssue.SG_OPEN) {
    return ["restrict_security_group", byIssue.SG_OPEN.resource_id];
  }
  if (byIssue.S3_PUBLIC) {
    return ["fix_s3_public_access", byIssue.S3_PUBLIC.resource_id];
  }
  if (byIssue.DB_UNENCRYPTED) {
    return ["encrypt_database", byIssue.DB_UNENCRYPTED.resource_id];
  }

  return ["scan_resources", null];
}

async function nextBestStep() {
  const [actionType, target] = getNextBestAction(currentState);
  if (availableActions.length === 0 || availableActions.includes(actionType)) {
    el("action-select").value = actionType;
  }
  el("resource-input").value = target || "";
  await applyAction(actionType, target);
}

async function autoRemediate() {
  if (autoRunning || demoRunning) {
    return;
  }

  autoRunning = true;
  const autoBtn = el("auto-btn");
  autoBtn.disabled = true;
  autoBtn.textContent = "Running Auto...";

  try {
    await resetTask(true);
    setStatus("auto run started for selected task.");

    const maxSteps = Math.max(Number(currentState?.task?.max_steps || 12), 1);
    setAutoProgress(0, maxSteps);
    for (let i = 0; i < maxSteps; i += 1) {
      if (currentState?.done) {
        break;
      }

      const [actionType, target] = getNextBestAction(currentState);
      if (availableActions.length === 0 || availableActions.includes(actionType)) {
        el("action-select").value = actionType;
      }
      el("resource-input").value = target || "";
      await applyAction(actionType, target);
      await new Promise((resolve) => setTimeout(resolve, 220));
    }

    if (currentState?.done) {
      setAutoProgress(Number(currentState.step_count || 0), maxSteps);
      setStatus(`auto run complete. final score ${Number(currentState.score || 0).toFixed(2)}.`);
      setHealth(true, "Auto complete");
    } else {
      setAutoProgress(Number(currentState?.step_count || 0), maxSteps);
      setStatus("auto run stopped at max steps.");
      setHealth(false, "Auto partial");
    }
  } catch (err) {
    setStatus(`auto run failed: ${err.message}`);
    setHealth(false, "Auto failed");
  } finally {
    autoRunning = false;
    autoBtn.disabled = false;
    autoBtn.textContent = "Run Task Auto";
  }
}

function setDemoResults(items) {
  stateEls.demoResults.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("div");
    row.className = `demo-result-item ${item.level}`;
    row.textContent = item.text;
    stateEls.demoResults.appendChild(row);
  }
}

function scoreLevel(score) {
  if (score >= 0.93) {
    return "ok";
  }
  if (score >= 0.8) {
    return "warn";
  }
  return "fail";
}

async function runTaskPlan(taskId) {
  el("task-select").value = taskId;
  await resetTask(false);

  const maxSteps = Math.max(Number(currentState?.task?.max_steps || 12), 1);
  for (let i = 0; i < maxSteps; i += 1) {
    if (currentState?.done) {
      break;
    }

    const [actionType, target] = getNextBestAction(currentState);
    await applyAction(actionType, target);
    await new Promise((resolve) => setTimeout(resolve, 260));
  }

  const latestState = await api("/state");
  renderState(latestState);
  return {
    taskId,
    score: Number(latestState.score || 0),
    done: Boolean(latestState.done),
    steps: Number(latestState.step_count || 0),
  };
}

async function runDemoMode() {
  if (demoRunning) {
    return;
  }

  demoRunning = true;
  const btn = el("demo-mode-btn");
  btn.disabled = true;
  btn.textContent = "Running Demo...";
  setAutoProgress(0, 0);
  resetTimeline();
  pushTimelineEvent({
    taskId: "all_tasks",
    time: nowStamp(),
    action: "demo_start",
    reward: "0.00",
    score: "0.00",
    step: "0",
    note: "Automated demo walkthrough started.",
    level: "warn",
  });
  setDemoResults([{ level: "warn", text: "Preparing demo tasks..." }]);

  const results = [];
  try {
    let tasks = availableTaskIds.length > 0 ? [...availableTaskIds] : getTaskSelectOptions();
    if (tasks.length === 0 && currentState?.task?.task_id) {
      tasks = [currentState.task.task_id];
    }
    if (tasks.length === 0) {
      throw new Error("No tasks available from metadata");
    }

    setDemoResults([{ level: "warn", text: `Running ${tasks.join(", ")}...` }]);

    for (const taskId of tasks) {
      const result = await runTaskPlan(taskId);
      results.push(result);
      setDemoResults(
        results.map((r) => ({
          level: scoreLevel(r.score),
          text: `${r.taskId} | score=${r.score.toFixed(2)} | steps=${r.steps} | done=${r.done ? "yes" : "no"}`,
        }))
      );
    }

    const avg = results.reduce((acc, x) => acc + x.score, 0) / results.length;
    const taskCount = results.length;
    setDemoResults([
      ...results.map((r) => ({
        level: scoreLevel(r.score),
        text: `${r.taskId} | score=${r.score.toFixed(2)} | steps=${r.steps} | done=${r.done ? "yes" : "no"}`,
      })),
      { level: scoreLevel(avg), text: `average_score=${avg.toFixed(2)} across ${taskCount} task${taskCount === 1 ? "" : "s"}` },
    ]);
    pushTimelineEvent({
      taskId: "all_tasks",
      time: nowStamp(),
      action: "demo_complete",
      reward: "0.00",
      score: avg.toFixed(2),
      step: "-",
      note: `Demo walkthrough finished across ${taskCount} task${taskCount === 1 ? "" : "s"}.`,
      level: scoreLevel(avg),
    });
    setHealth(true, "Demo complete");
    setStatus(`demo complete. average score ${avg.toFixed(2)}.`);
  } catch (err) {
    setHealth(false, "Demo failed");
    setStatus(`demo failed: ${err.message}`);
    setDemoResults([
      ...results.map((r) => ({
        level: scoreLevel(r.score),
        text: `${r.taskId} | score=${r.score.toFixed(2)} | steps=${r.steps} | done=${r.done ? "yes" : "no"}`,
      })),
      { level: "fail", text: `demo_error=${err.message}` },
    ]);
    pushTimelineEvent({
      taskId: "all_tasks",
      time: nowStamp(),
      action: "demo_error",
      reward: "0.00",
      score: "0.00",
      step: "-",
      note: `error=${err.message}`,
      level: "fail",
    });
  } finally {
    demoRunning = false;
    btn.disabled = false;
    btn.textContent = "Demo Mode";
  }
}

function applyCardTilt() {
  for (const card of document.querySelectorAll(".tilt")) {
    card.addEventListener("mousemove", (ev) => {
      const rect = card.getBoundingClientRect();
      const x = (ev.clientX - rect.left) / rect.width;
      const y = (ev.clientY - rect.top) / rect.height;
      const rx = (0.5 - y) * 8;
      const ry = (x - 0.5) * 8;
      card.style.transform = `perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg)`;
    });
    card.addEventListener("mouseleave", () => {
      card.style.transform = "perspective(900px) rotateX(0deg) rotateY(0deg)";
    });
  }
}

function initTips() {
  for (const node of document.querySelectorAll(".tip[data-tip]")) {
    const text = node.getAttribute("data-tip");
    if (text) {
      node.setAttribute("title", text);
      node.setAttribute("aria-label", text);
    }
  }
}

el("reset-btn").addEventListener("click", () => resetTask(true));
const handleTaskSelectionChange = () => {
  if (taskResetTimer) {
    clearTimeout(taskResetTimer);
  }
  taskResetTimer = setTimeout(() => {
    resetTask(true);
  }, 0);
};

el("task-select").addEventListener("change", handleTaskSelectionChange);
el("task-select").addEventListener("input", handleTaskSelectionChange);
el("step-btn").addEventListener("click", applyStep);
el("quick-next-btn").addEventListener("click", nextBestStep);
el("refresh-btn").addEventListener("click", refreshState);
el("auto-btn").addEventListener("click", autoRemediate);
el("demo-mode-btn").addEventListener("click", runDemoMode);
el("clear-timeline-btn").addEventListener("click", resetTimeline);

async function initApp() {
  await loadTaskCatalog();
  await loadActionCatalog();
  await loadResourceCatalog();
  await resetTask(false);
  resetTimeline();
  renderTimeline();
  applyCardTilt();
  initTips();
}

initApp();
