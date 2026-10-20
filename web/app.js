const form = document.getElementById("question-form");
const question = document.getElementById("question");
const submitButton = document.getElementById("submit-button");
const count = document.getElementById("character-count");
const status = document.getElementById("status");
const answerCard = document.getElementById("answer-card");
const answer = document.getElementById("answer");
const uyghurAnswerCard = document.getElementById("uyghur-answer-card");
const uyghurAnswerZh = document.getElementById("uyghur-answer-zh");
const uyghurAnswerUg = document.getElementById("uyghur-answer-ug");
const speakChineseButton = document.getElementById("speak-chinese");
const speakUyghurButton = document.getElementById("speak-uyghur");
const textMode = document.getElementById("text-mode");
const uyghurTextMode = document.getElementById("uyghur-text-mode");
const imageMode = document.getElementById("image-mode");
const audioMode = document.getElementById("audio-mode");
const chineseAudioMode = document.getElementById("chinese-audio-mode");
const textPanel = document.getElementById("text-panel");
const uyghurTextPanel = document.getElementById("uyghur-text-panel");
const imagePanel = document.getElementById("image-panel");
const audioPanel = document.getElementById("audio-panel");
const chineseAudioPanel = document.getElementById("chinese-audio-panel");
const uyghurTextForm = document.getElementById("uyghur-text-form");
const uyghurTextQuestion = document.getElementById("uyghur-text-question");
const uyghurTextCount = document.getElementById("uyghur-text-count");
const uyghurTextSubmit = document.getElementById("uyghur-text-submit");
const typedUyghurUnderstanding = document.getElementById("typed-uyghur-understanding");
const typedUyghurQuestionZh = document.getElementById("typed-uyghur-question-zh");
const recordButton = document.getElementById("record-button");
const stopVoiceButton = document.getElementById("stop-voice-button");
const recordingHint = document.getElementById("recording-hint");
const chineseRecordButton = document.getElementById("chinese-record-button");
const chineseStopButton = document.getElementById("chinese-stop-button");
const chineseRecordingHint = document.getElementById("chinese-recording-hint");
const chineseLiveTranscript = document.getElementById("chinese-live-transcript");
const transcriptionCard = document.getElementById("transcription-card");
const transcription = document.getElementById("transcription");
const transcriptionRaw = document.getElementById("transcription-raw");
const transcriptionCorrections = document.getElementById("transcription-corrections");
const imageForm = document.getElementById("image-form");
const imageFile = document.getElementById("image-file");
const imageQuestion = document.getElementById("image-question");
const imagePreview = document.getElementById("image-preview");
const imageSubmitButton = document.getElementById("image-submit-button");
const observationCard = document.getElementById("observation-card");
const observation = document.getElementById("observation");
const stopAnswerButton = document.getElementById("stop-answer");
const historyToggle = document.getElementById("history-toggle");
const historyDrawer = document.getElementById("history-drawer");
const historyClose = document.getElementById("history-close");
const historyList = document.getElementById("history-list");
const newConversationButton = document.getElementById("new-conversation");
const conversationTurns = document.getElementById("conversation-turns");
const appShell = document.querySelector(".page-shell");
let conversationId = null;
let currentConversationData = null;
let activeTurnInAnswer = null;
let conversationUiSession = 0;
let activeTextController = null;
let activeUyghurTextController = null;
let activeImageController = null;

async function apiFetch(path, options = {}) {
  return fetch(path, { ...options, credentials: "same-origin" });
}

function selectionKey() { return "shennong_conversation_id"; }

async function conversationApi(path, options = {}) {
  const response = await apiFetch(path, options);
  const data = await readApiResponse(response, "历史对话");
  if (!response.ok) throw new Error(data.error || "历史对话服务暂时不可用。");
  return data;
}

async function refreshHistoryList() {
  const data = await conversationApi("/api/conversations");
  historyList.replaceChildren();
  for (const item of data.conversations) {
    const row = document.createElement("div");
    row.className = "history-row";
    const open = document.createElement("button");
    open.type = "button";
    open.className = "history-open";
    open.textContent = item.title;
    open.title = item.title;
    open.setAttribute("aria-current", String(item.id === conversationId));
    open.addEventListener("click", () => openConversation(item.id));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "history-delete";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `删除对话：${item.title}`);
    remove.addEventListener("click", async () => {
      if (!window.confirm(`删除“${item.title}”及其全部对话记录？此操作无法撤销。`)) return;
      try {
        await conversationApi(`/api/conversations/${item.id}`, { method: "DELETE" });
        if (item.id === conversationId) startNewConversation();
        await refreshHistoryList();
      } catch (error) { status.textContent = error.message; }
    });
    row.append(open, remove);
    historyList.append(row);
  }
  if (!data.conversations.length) {
    const empty = document.createElement("p");
    empty.className = "history-empty";
    empty.textContent = "还没有保存的对话";
    historyList.append(empty);
  }
}

function renderConversationTurns() {
  conversationTurns.replaceChildren();
  const turns = currentConversationData?.turns || [];
  const visible = turns.filter((turn) => turn.id !== activeTurnInAnswer);
  conversationTurns.hidden = visible.length === 0;
  for (const turn of visible) {
    const item = document.createElement("article");
    item.className = "conversation-turn";
    const original = document.createElement("p");
    original.className = "turn-original";
    original.textContent = turn.original_input === "[仅图片]" ? UiLocale.translate("上传了一张农牧业照片") : turn.original_input;
    item.append(original);
    if (turn.original_input !== turn.question_zh || turn.input_kind === "image") {
      const understood = document.createElement("p");
      understood.className = "turn-understood";
      understood.textContent = `理解为：${turn.question_zh}`;
      item.append(understood);
    }
    if (turn.observation) {
      const seen = document.createElement("p");
      seen.className = "turn-observation";
      seen.textContent = `照片观察：${turn.observation}`;
      item.append(seen);
    }
    const reply = document.createElement("div");
    reply.className = "turn-reply";
    const zh = document.createElement("div");
    zh.className = "answer-text";
    zh.lang = "zh-CN";
    renderAnswer(turn.answer_zh, zh);
    reply.append(zh);
    const ug = document.createElement("div");
    ug.className = "answer-text turn-uyghur";
    ug.lang = "ug";
    ug.dir = "rtl";
    if (turn.answer_ug) renderAnswer(turn.answer_ug, ug);
    else ug.textContent = UiLocale.translate(turn.translation_status === "failed" ? "维文翻译失败，中文回答已保存。" : "维文翻译未完成。");
    reply.append(ug);
    item.append(reply);
    const actions = document.createElement("div");
    actions.className = "turn-actions";
    const view = document.createElement("button");
    view.type = "button";
    view.textContent = "查看与朗读";
    view.addEventListener("click", () => {
      stopAllSpeech();
      activeTurnInAnswer = turn.id;
      renderConversationTurns();
      renderAnswer(turn.answer_zh, uyghurAnswerZh);
      if (turn.answer_ug) renderAnswer(turn.answer_ug, uyghurAnswerUg);
      else uyghurAnswerUg.textContent = UiLocale.translate(turn.translation_status === "failed" ? "维文翻译失败。" : "维文翻译未完成。");
      typedUyghurQuestionZh.textContent = turn.question_zh;
      typedUyghurUnderstanding.hidden = false;
      observationCard.hidden = !turn.observation;
      observation.textContent = turn.observation;
      uyghurAnswerCard.hidden = false;
      uyghurAnswerCard.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    actions.append(view);
    if (turn.translation_status !== "complete") {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "重试维文翻译";
      retry.addEventListener("click", async () => {
        retry.disabled = true;
        retry.textContent = "翻译中…";
        try {
          await conversationApi(`/api/turns/${turn.id}/retry-translation`, {
            method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
          });
          await refreshCurrentConversation(false);
          status.textContent = "维文翻译已补全。";
        } catch (error) {
          status.textContent = error.message;
          retry.disabled = false;
          retry.textContent = "重试维文翻译";
        }
      });
      actions.append(retry);
    }
    item.append(actions);
    conversationTurns.append(item);
  }
  if (visible.length) conversationTurns.scrollTop = conversationTurns.scrollHeight;
}


function cancelActiveQuestions() {
  conversationUiSession += 1;
  activeTextController?.abort();
  activeUyghurTextController?.abort();
  activeImageController?.abort();
  cancelVoiceSession("已停止当前对话");
  cancelChineseSpeechRecognition("已停止中文语音识别");
  stopAllSpeech();
}

function clearActiveAnswer() {
  answerCard.hidden = true;
  uyghurAnswerCard.hidden = true;
  transcriptionCard.hidden = true;
  observationCard.hidden = true;
  typedUyghurUnderstanding.hidden = true;
  answer.replaceChildren();
  uyghurAnswerZh.replaceChildren();
  uyghurAnswerUg.replaceChildren();
  status.textContent = "";
}

function startNewConversation() {
  cancelActiveQuestions();
  conversationId = null;
  currentConversationData = null;
  activeTurnInAnswer = null;
  localStorage.removeItem(selectionKey());
  clearActiveAnswer();
  renderConversationTurns();
  historyDrawer.hidden = true;
  historyToggle.setAttribute("aria-expanded", "false");
  question.value = "";
  uyghurTextQuestion.value = "";
  imageQuestion.value = "";
  selectMode(composerLanguage === "ug" ? "uyghur-text" : "text");
  refreshHistoryList().catch(() => {});
}

async function openConversation(id) {
  cancelActiveQuestions();
  const session = conversationUiSession;
  try {
    const data = await conversationApi(`/api/conversations/${id}`);
    if (session !== conversationUiSession) return;
    conversationId = id;
    currentConversationData = data;
    activeTurnInAnswer = null;
    localStorage.setItem(selectionKey(), id);
    clearActiveAnswer();
    renderConversationTurns();
    historyDrawer.hidden = true;
    historyToggle.setAttribute("aria-expanded", "false");
    await refreshHistoryList();
  } catch (error) {
    if (id === localStorage.getItem(selectionKey())) localStorage.removeItem(selectionKey());
    status.textContent = error.message;
    refreshHistoryList().catch(() => {});
  }
}

async function ensureConversation() {
  if (conversationId) return conversationId;
  const session = conversationUiSession;
  const data = await conversationApi("/api/conversations", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  });
  if (session !== conversationUiSession) throw new DOMException("对话已切换", "AbortError");
  conversationId = data.id;
  localStorage.setItem(selectionKey(), data.id);
  refreshHistoryList().catch(() => {});
  return data.id;
}

async function refreshCurrentConversation(showCurrentAnswer = true) {
  if (!conversationId) return;
  const id = conversationId;
  const data = await conversationApi(`/api/conversations/${id}`);
  if (id !== conversationId) return;
  currentConversationData = data;
  activeTurnInAnswer = showCurrentAnswer && !uyghurAnswerCard.hidden ? data.turns.at(-1)?.id || null : null;
  renderConversationTurns();
  refreshHistoryList().catch(() => {});
}

historyToggle.addEventListener("click", () => {
  historyDrawer.hidden = !historyDrawer.hidden;
  historyToggle.setAttribute("aria-expanded", String(!historyDrawer.hidden));
  if (!historyDrawer.hidden) refreshHistoryList().catch((error) => { status.textContent = error.message; });
});
historyClose.addEventListener("click", () => {
  historyDrawer.hidden = true;
  historyToggle.setAttribute("aria-expanded", "false");
});
newConversationButton.addEventListener("click", startNewConversation);
stopAnswerButton.addEventListener("click", () => {
  cancelActiveQuestions();
  status.classList.remove("working");
  status.textContent = "已停止本次生成；已完成的中文回答仍可在历史记录中查看。";
  refreshCurrentConversation(false).catch(() => {});
});

function addInlineText(parent, value) {
  const parts = value.split(/(\*\*[^*]+\*\*)/g);
  for (const part of parts) {
    if (part.startsWith("**") && part.endsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = part.slice(2, -2);
      parent.appendChild(strong);
    } else {
      parent.appendChild(document.createTextNode(part));
    }
  }
}

async function readApiResponse(response, endpointName) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json();
  const body = await response.text();
  if (response.status === 404) {
    throw new Error(`${endpointName}接口返回 404：当前运行的可能是旧版服务。请关闭主网页服务窗口，再从“新疆农牧小助手”根目录启动 start.cmd。`);
  }
  throw new Error(`本机服务返回了非 JSON 错误（HTTP ${response.status}）：${body.slice(0, 160)}`);
}

function partialJsonStringField(raw, field) {
  const marker = `"${field}"`;
  const keyIndex = raw.indexOf(marker);
  if (keyIndex < 0) return "";
  const colonIndex = raw.indexOf(":", keyIndex + marker.length);
  if (colonIndex < 0) return "";
  const quoteIndex = raw.indexOf('"', colonIndex + 1);
  if (quoteIndex < 0) return "";

  let encoded = "";
  for (let index = quoteIndex + 1; index < raw.length; index += 1) {
    const character = raw[index];
    if (character === '"') break;
    if (character === "\\") {
      if (index + 1 >= raw.length) break;
      encoded += character + raw[index + 1];
      index += 1;
      if (raw[index] === "u") {
        const digits = raw.slice(index + 1, index + 5);
        if (digits.length < 4) break;
        encoded += digits;
        index += 4;
      }
    } else {
      encoded += character;
    }
  }

  // A network chunk can end in the middle of an escape sequence. Keep the
  // longest valid JSON-string prefix so the UI can still show earlier text.
  for (let length = encoded.length; length >= 0; length -= 1) {
    try {
      return JSON.parse(`"${encoded.slice(0, length)}"`);
    } catch {
      // Trim only the incomplete tail; a later chunk will complete it.
    }
  }
  return "";
}

function showUyghurTranscription(result) {
  if (typeof result.transcription !== "string" || !result.transcription.trim()) return;
  transcription.textContent = result.transcription;
  transcriptionRaw.textContent = typeof result.transcription_raw === "string" && result.transcription_raw.trim()
    ? result.transcription_raw : result.transcription;
  const replacements = Array.isArray(result.corrections) ? result.corrections : [];
  transcriptionCorrections.replaceChildren();
  if (replacements.length) {
    const label = document.createElement("strong");
    label.textContent = "已按词表替换：";
    transcriptionCorrections.append(label, document.createTextNode(" "));
    replacements.forEach((item, index) => {
      if (index) transcriptionCorrections.append(document.createTextNode("；"));
      transcriptionCorrections.append(document.createTextNode(
        `${item.heard || ""} → ${item.standard || ""}（${item.chinese || ""}）`
      ));
    });
    transcriptionCorrections.hidden = false;
  } else {
    transcriptionCorrections.hidden = true;
  }
  transcriptionCard.hidden = false;
}

function renderAnswer(value, target = answer) {
  target.replaceChildren();
  let list = null;
  for (const line of value.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) {
      list = null;
      continue;
    }
    const heading = trimmed.match(/^#{1,4}\s+(.+)$/);
    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    const numbered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (heading) {
      const element = document.createElement("h3");
      addInlineText(element, heading[1]);
      target.appendChild(element);
      list = null;
    } else if (bullet || numbered) {
      const kind = numbered ? "ol" : "ul";
      if (!list || list.tagName.toLowerCase() !== kind) {
        list = document.createElement(kind);
        target.appendChild(list);
      }
      const item = document.createElement("li");
      addInlineText(item, (bullet || numbered)[1]);
      list.appendChild(item);
    } else {
      const element = document.createElement("p");
      addInlineText(element, trimmed);
      target.appendChild(element);
      list = null;
    }
  }
}

async function consumeBilingualStream(response, options = {}) {
  if (!response.ok || !(response.headers.get("content-type") || "").includes("text/event-stream")) {
    const result = await readApiResponse(response, options.endpointName || "双语问答");
    throw new Error(result.error || "请求未能启动流式响应。请确认腾讯和神农密钥已配置。");
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("浏览器不支持读取流式回答，请更新 Edge 或 Chrome。 ");
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let chinese = "";
  let finalResult = null;
  let translationFailed = false;
  const handleFrame = (frame) => {
    const lines = frame.split(/\r?\n/);
    const eventName = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
    const dataText = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
    if (!dataText) return;
    let data;
    try { data = JSON.parse(dataText); } catch { throw new Error("收到无法解析的流式数据，请重试。"); }
    if (eventName === "transcript") {
      showUyghurTranscription(data);
      options.onTranscript?.(data);
    } else if (eventName === "question_info") {
      if (data.transcription) showUyghurTranscription(data);
      options.onQuestionInfo?.(data);
    } else if (eventName === "observation") {
      if (typeof data.observation === "string") {
        observation.textContent = data.observation;
        observationCard.hidden = false;
      }
      options.onObservation?.(data);
    } else if (eventName === "question") {
      if (typeof data.question_zh === "string" && data.question_zh.trim()) {
        typedUyghurQuestionZh.textContent = data.question_zh;
        typedUyghurUnderstanding.hidden = false;
      }
      status.textContent = "腾讯已完成问题翻译，神农正在生成中文回答…";
    } else if (eventName === "answer_zh_token") {
      if (typeof data.content !== "string") return;
      chinese += data.content;
      renderAnswer(chinese, uyghurAnswerZh);
      uyghurAnswerCard.hidden = false;
      uyghurAnswerUg.textContent = "";
    } else if (eventName === "answer_zh_done") {
      if (typeof data.answer_zh === "string") chinese = data.answer_zh;
      renderAnswer(chinese, uyghurAnswerZh);
      uyghurAnswerUg.textContent = "正在翻译…";
      uyghurAnswerCard.hidden = false;
    } else if (eventName === "translation_status") {
      status.textContent = data.message || "中文回答已完成，正在翻译为维吾尔语…";
    } else if (eventName === "done") {
      finalResult = data;
      renderAnswer(data.answer_zh || chinese, uyghurAnswerZh);
      renderAnswer(data.answer_ug || "", uyghurAnswerUg);
      uyghurAnswerCard.hidden = false;
    } else if (eventName === "translation_error") {
      translationFailed = true;
      if (typeof data.answer_zh === "string") renderAnswer(data.answer_zh, uyghurAnswerZh);
      uyghurAnswerUg.textContent = UiLocale.translate(data.error || "腾讯中转维失败；中文回答已保留。");
      uyghurAnswerCard.hidden = false;
      status.textContent = data.error || "腾讯中转维失败；中文回答已保留。";
    } else if (eventName === "error") {
      throw new Error(data.error || "神农流式回答中断，请重试。");
    }
  };
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() || "";
    frames.forEach(handleFrame);
    if (done) break;
  }
  if (buffer.trim()) handleFrame(buffer);
  if (!finalResult && !translationFailed) throw new Error("流式连接结束，但没有收到完整回答。");
  return finalResult || { answer_zh: chinese, answer_ug: "", translation_failed: true };
}

function selectMode(mode, preserveResult = false) {
  syncComposerMode(mode);
  stopAllSpeech();
  if (mode !== "audio" && (recording || wantsRecording || transcriptionBusy)) cancelVoiceSession("已取消本次语音识别和回答");
  if (mode !== "chinese-audio" && chineseSpeechRequested) cancelChineseSpeechRecognition("已取消本次中文语音识别");
  const isUyghurText = mode === "uyghur-text";
  const isImage = mode === "image";
  const isAudio = mode === "audio";
  const isChineseAudio = mode === "chinese-audio";
  textPanel.hidden = isUyghurText || isImage || isAudio || isChineseAudio;
  uyghurTextPanel.hidden = !isUyghurText;
  imagePanel.hidden = !isImage;
  audioPanel.hidden = !isAudio;
  chineseAudioPanel.hidden = !isChineseAudio;
  textMode.classList.toggle("active", mode === "text");
  uyghurTextMode.classList.toggle("active", isUyghurText);
  imageMode.classList.toggle("active", isImage);
  audioMode.classList.toggle("active", isAudio);
  chineseAudioMode.classList.toggle("active", isChineseAudio);
  textMode.setAttribute("aria-pressed", String(mode === "text"));
  uyghurTextMode.setAttribute("aria-pressed", String(isUyghurText));
  imageMode.setAttribute("aria-pressed", String(isImage));
  audioMode.setAttribute("aria-pressed", String(isAudio));
  chineseAudioMode.setAttribute("aria-pressed", String(isChineseAudio));
  if (!preserveResult) {
    observationCard.hidden = true;
    answerCard.hidden = true;
    uyghurAnswerCard.hidden = true;
    typedUyghurUnderstanding.hidden = true;
    transcriptionCard.hidden = true;
    status.textContent = "";
  }
}

textMode.addEventListener("click", () => selectMode("text"));
chineseAudioMode.addEventListener("click", () => selectMode("chinese-audio"));
uyghurTextMode.addEventListener("click", () => selectMode("uyghur-text"));
imageMode.addEventListener("click", () => selectMode("image"));
audioMode.addEventListener("click", () => selectMode("audio"));

const BrowserSpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let chineseSpeechRecognition = null;
let chineseSpeechRequested = false;
let chineseSpeechPointerId = null;
let chineseSpeechFinalText = "";
let chineseSpeechLimitTimer = null;
let chineseSpeechRecognitionEnded = false;
const MAX_CHINESE_SPEECH_MS = 45_000;

function setChineseRecordState(state) {
  chineseRecordButton.classList.toggle("recording", state === "recording");
  chineseRecordButton.classList.toggle("busy", state === "busy");
  chineseRecordButton.disabled = state === "busy";
  chineseRecordButton.setAttribute("aria-pressed", String(state === "recording"));
  chineseRecordButton.textContent = state === "recording"
    ? "正在识别，松开结束"
    : state === "busy" ? "正在整理识别结果…" : "按住说话";
  chineseStopButton.hidden = state === "idle";
}

function finishChineseSpeechRecognition(errorMessage = "") {
  window.clearTimeout(chineseSpeechLimitTimer);
  chineseSpeechLimitTimer = null;
  chineseSpeechRequested = false;
  chineseSpeechPointerId = null;
  setChineseRecordState("busy");
  if (errorMessage) {
    status.textContent = errorMessage;
    chineseRecordingHint.textContent = "请检查麦克风权限和网络连接后重试。";
    setChineseRecordState("idle");
    chineseSpeechRecognition = null;
    return;
  }

  const recognizedText = chineseSpeechFinalText.trim();
  if (!recognizedText) {
    status.textContent = "没有识别到中文，请靠近麦克风再试一次。";
    chineseRecordingHint.textContent = "没有识别到文字，请重新按住说话。";
    chineseLiveTranscript.textContent = "识别文字将在这里显示";
    setChineseRecordState("idle");
    chineseSpeechRecognition = null;
    return;
  }

  question.value = recognizedText.slice(0, 2000);
  question.dispatchEvent(new Event("input", { bubbles: true }));
  question.dataset.fromVoice = "true";
  selectMode("text");
  status.textContent = "中文语音已转成文字并填入问题框，请核对后点击“获取回答”。";
  chineseRecordingHint.textContent = "识别完成；你可以在文字提问框中修改后提交。";
  chineseSpeechRecognition = null;
  setChineseRecordState("idle");
  textPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  question.focus({ preventScroll: true });
}

function beginChineseSpeechRecognition() {
  if (chineseSpeechRequested || transcriptionBusy) return;
  if (!BrowserSpeechRecognition) {
    status.textContent = "当前浏览器没有中文语音识别功能，请使用最新版 Edge 或 Chrome。";
    chineseRecordingHint.textContent = "语音识别功能不可用。";
    return;
  }

  const recognition = new BrowserSpeechRecognition();
  chineseSpeechRecognition = recognition;
  chineseSpeechRequested = true;
  chineseSpeechRecognitionEnded = false;
  chineseSpeechFinalText = "";
  chineseLiveTranscript.textContent = "正在聆听…";
  chineseRecordingHint.textContent = "正在聆听普通话；请说清楚作物、牲畜和症状名称。松开按钮结束。";
  status.textContent = "";
  recognition.lang = "zh-CN";
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    setChineseRecordState("recording");
  };
  recognition.onresult = (event) => {
    if (chineseSpeechRecognitionEnded) return;
    let interimText = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      const text = result[0]?.transcript || "";
      if (result.isFinal) chineseSpeechFinalText += text;
      else interimText += text;
    }
    const combined = `${chineseSpeechFinalText}${interimText}`.trim();
    chineseLiveTranscript.textContent = combined || "正在聆听…";
  };
  recognition.onerror = (event) => {
    if (chineseSpeechRecognitionEnded) return;
    const messages = {
      "not-allowed": "浏览器没有麦克风权限。请在地址栏的网站权限中允许麦克风后重试。",
      "service-not-allowed": "浏览器语音识别服务不可用，请检查网络或改用最新版 Edge / Chrome。",
      "audio-capture": "没有找到可用麦克风，请连接或启用麦克风后重试。",
      network: "中文语音识别连接失败，请检查网络后重试。",
      "no-speech": "没有听到语音，请靠近麦克风后重试。",
    };
    chineseSpeechRecognitionEnded = true;
    finishChineseSpeechRecognition(messages[event.error] || `中文语音识别失败：${event.error || "请重试"}`);
  };
  recognition.onend = () => {
    if (chineseSpeechRecognitionEnded) return;
    chineseSpeechRecognitionEnded = true;
    finishChineseSpeechRecognition();
  };

  try {
    recognition.start();
    setChineseRecordState("recording");
    chineseSpeechLimitTimer = window.setTimeout(() => stopChineseSpeechRecognition("达到 45 秒上限，正在整理识别结果…"), MAX_CHINESE_SPEECH_MS);
  } catch (error) {
    chineseSpeechRecognitionEnded = true;
    finishChineseSpeechRecognition(error.name === "NotAllowedError"
      ? "浏览器没有麦克风权限。请在地址栏的网站权限中允许麦克风后重试。"
      : `无法启动中文语音识别：${error.message || String(error)}`);
  }
}

function cancelChineseSpeechRecognition(message = "已取消本次中文语音识别") {
  const recognition = chineseSpeechRecognition;
  if (!recognition && !chineseSpeechRequested) return;
  chineseSpeechRecognitionEnded = true;
  chineseSpeechRequested = false;
  chineseSpeechPointerId = null;
  chineseSpeechFinalText = "";
  window.clearTimeout(chineseSpeechLimitTimer);
  chineseSpeechLimitTimer = null;
  try { recognition?.abort(); } catch { /* Recognition may already have ended. */ }
  chineseSpeechRecognition = null;
  chineseLiveTranscript.textContent = "识别文字将在这里显示";
  chineseRecordingHint.textContent = message;
  setChineseRecordState("idle");
  status.classList.remove("working");
  status.textContent = message;
}

function stopChineseSpeechRecognition(hint = "松开完成，正在整理识别结果…") {
  const recognition = chineseSpeechRecognition;
  if (!recognition || !chineseSpeechRequested) return;
  chineseSpeechRequested = false;
  window.clearTimeout(chineseSpeechLimitTimer);
  chineseSpeechLimitTimer = null;
  chineseRecordingHint.textContent = hint;
  setChineseRecordState("busy");
  try {
    recognition.stop();
  } catch {
    if (!chineseSpeechRecognitionEnded) {
      chineseSpeechRecognitionEnded = true;
      finishChineseSpeechRecognition();
    }
  }
}

chineseRecordButton.addEventListener("pointerdown", (event) => {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  event.preventDefault();
  chineseSpeechPointerId = event.pointerId;
  chineseRecordButton.setPointerCapture?.(event.pointerId);
  beginChineseSpeechRecognition();
});
chineseStopButton.addEventListener("click", () => cancelChineseSpeechRecognition());
chineseRecordButton.addEventListener("pointerup", (event) => {
  if (chineseSpeechPointerId !== event.pointerId) return;
  stopChineseSpeechRecognition();
});
chineseRecordButton.addEventListener("pointercancel", () => stopChineseSpeechRecognition());
chineseRecordButton.addEventListener("lostpointercapture", () => stopChineseSpeechRecognition());
chineseRecordButton.addEventListener("keydown", (event) => {
  if ((event.code === "Space" || event.code === "Enter") && !event.repeat) {
    event.preventDefault();
    beginChineseSpeechRecognition();
  }
});
chineseRecordButton.addEventListener("keyup", (event) => {
  if (event.code === "Space" || event.code === "Enter") {
    event.preventDefault();
    stopChineseSpeechRecognition();
  }
});
window.addEventListener("blur", () => stopChineseSpeechRecognition());
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopChineseSpeechRecognition();
});

uyghurTextQuestion.addEventListener("input", () => {
  uyghurTextCount.textContent = `${uyghurTextQuestion.value.length} / 2000 字`;
});

uyghurTextForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = uyghurTextQuestion.value.trim();
  if (!value) {
    status.textContent = "请先输入维吾尔语问题。";
    uyghurTextQuestion.focus();
    return;
  }

  stopAllSpeech();
  uyghurTextSubmit.disabled = true;
  uyghurTextSubmit.textContent = "正在翻译并回答…";
  status.textContent = "正在按词表校正维文，并由腾讯翻译成中文…";
  status.classList.add("working");
  typedUyghurUnderstanding.hidden = true;
  uyghurAnswerCard.hidden = true;
  uyghurAnswerZh.replaceChildren();
  uyghurAnswerUg.replaceChildren();
  const controller = new AbortController();
  activeUyghurTextController = controller;
  const uiSession = conversationUiSession;
  const timer = window.setTimeout(() => controller.abort(), 180_000);
  try {
    const id = await ensureConversation();
    const response = await apiFetch("/api/ask-uyghur-text-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: value, conversation_id: id }),
      signal: controller.signal,
    });
    const result = await consumeBilingualStream(response, { endpointName: "维语文字问答" });
    if (uiSession !== conversationUiSession) return;
    await refreshCurrentConversation();
    uyghurTextQuestion.value = "";
    uyghurTextQuestion.dispatchEvent(new Event("input", { bubbles: true }));
    status.textContent = result.translation_failed
      ? "中文回答已完成，但维文翻译失败；可保留中文结果后重试。"
      : "双语回答已完成；点击对应喇叭才会朗读。";
    uyghurAnswerCard.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (uiSession !== conversationUiSession) return;
    refreshCurrentConversation(false).catch(() => {});
    status.textContent = error.name === "AbortError" ? "等待神农回答超时，请稍后重试。" : (error.message || "请求失败，请稍后重试。");
  } finally {
    window.clearTimeout(timer);
    if (activeUyghurTextController === controller) activeUyghurTextController = null;
    status.classList.remove("working");
    uyghurTextSubmit.disabled = false;
    uyghurTextSubmit.innerHTML = '获取双语回答 <span aria-hidden="true">↗</span>';
  }
});

imageFile.addEventListener("change", () => {
  imagePreview.hidden = true;
  imagePreview.removeAttribute("src");
  const file = imageFile.files?.[0];
  if (!file) return;
  if (!["image/jpeg", "image/png"].includes(file.type) || file.size > 4 * 1024 * 1024) {
    status.textContent = "请选择不超过 4 MB 的 JPG 或 PNG 照片。";
    return;
  }
  imagePreview.src = URL.createObjectURL(file);
  imagePreview.hidden = false;
  imagePreview.onload = () => URL.revokeObjectURL(imagePreview.src);
  status.textContent = "";
});

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("文件读取失败，请重新选择。"));
    reader.readAsDataURL(file);
  });
}

question.addEventListener("input", () => {
  count.textContent = `${question.value.length} / 2000 字`;
});

let mediaRecorder = null;
let mediaStream = null;
let audioChunks = [];
let recording = false;
let wantsRecording = false;
let transcriptionBusy = false;
let voiceSessionId = 0;
let activeVoiceRequestController = null;
let activePointerId = null;
let recordingStartedAt = 0;
let recordingLimitTimer = null;
const MAX_RECORDING_MS = 45_000;
const MAX_RECORDING_BYTES = 8 * 1024 * 1024;

function stopMicrophoneTracks() {
  mediaStream?.getTracks().forEach((track) => track.stop());
  mediaStream = null;
}

function setRecordButtonState(state) {
  recordButton.classList.toggle("recording", state === "recording");
  recordButton.classList.toggle("busy", state === "busy");
  recordButton.disabled = state === "busy";
  recordButton.setAttribute("aria-pressed", String(state === "recording"));
  recordButton.textContent = state === "recording" ? "正在录音，松开结束" : "按住说话";
  stopVoiceButton.hidden = state === "idle";
}

async function beginVoiceRecording() {
  if (recording || wantsRecording || transcriptionBusy) return;
  const sessionId = ++voiceSessionId;
  wantsRecording = true;
  status.textContent = "";
  transcriptionCard.hidden = true;
  answerCard.hidden = true;
  uyghurAnswerCard.hidden = true;
  recordingHint.textContent = "正在连接麦克风…";
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    wantsRecording = false;
    status.textContent = "当前浏览器不支持网页录音，请使用最新版 Edge 或 Chrome。";
    recordingHint.textContent = "按住按钮开始录音，松开后识别";
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    if (sessionId !== voiceSessionId || !wantsRecording) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    mediaStream = stream;
    const supportedMime = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"]
      .find((mime) => MediaRecorder.isTypeSupported(mime));
    const recorder = supportedMime ? new MediaRecorder(stream, { mimeType: supportedMime }) : new MediaRecorder(stream);
    mediaRecorder = recorder;
    audioChunks = [];
    recorder.addEventListener("dataavailable", (event) => {
      if (sessionId === voiceSessionId && event.data?.size) audioChunks.push(event.data);
    });
    recorder.addEventListener("error", (event) => {
      if (sessionId !== voiceSessionId) return;
      status.textContent = event.error?.message || "浏览器录音失败，请检查麦克风后重试。";
    });
    recorder.addEventListener("stop", () => finishVoiceRecording(sessionId, recorder), { once: true });
    recorder.start();
    recording = true;
    recordingStartedAt = performance.now();
    setRecordButtonState("recording");
    recordingHint.textContent = "正在录音…松开按钮结束";
    recordingLimitTimer = window.setTimeout(() => stopVoiceRecording("达到 45 秒上限，正在识别…"), MAX_RECORDING_MS);
  } catch (error) {
    if (sessionId !== voiceSessionId) return;
    wantsRecording = false;
    stopMicrophoneTracks();
    recordingHint.textContent = "按住按钮开始录音，松开后识别";
    if (["NotAllowedError", "PermissionDeniedError"].includes(error.name)) {
      status.textContent = "麦克风权限被拒绝。请在地址栏左侧的网站权限中允许麦克风，再试一次。";
    } else if (error.name === "NotFoundError") {
      status.textContent = "没有找到可用麦克风，请连接或启用麦克风后重试。";
    } else {
      status.textContent = `无法开始录音：${error.message || String(error)}`;
    }
  }
}

function stopVoiceRecording(message = "松开完成，正在本机识别…") {
  if (!recording && !wantsRecording) return;
  wantsRecording = false;
  if (!recording) {
    stopMicrophoneTracks();
    recordingHint.textContent = "按住按钮开始录音，松开后识别";
    return;
  }
  recording = false;
  window.clearTimeout(recordingLimitTimer);
  setRecordButtonState("idle");
  recordingHint.textContent = message;
  if (mediaRecorder?.state === "recording") mediaRecorder.stop();
  else stopMicrophoneTracks();
}

function cancelVoiceSession(message = "已取消本次语音识别和回答") {
  if (!recording && !wantsRecording && !transcriptionBusy) return;
  voiceSessionId += 1;
  wantsRecording = false;
  recording = false;
  transcriptionBusy = false;
  activePointerId = null;
  window.clearTimeout(recordingLimitTimer);
  activeVoiceRequestController?.abort();
  activeVoiceRequestController = null;
  audioChunks = [];
  if (mediaRecorder?.state === "recording") {
    try { mediaRecorder.stop(); } catch { /* Recorder may already be stopping. */ }
  }
  stopMicrophoneTracks();
  setRecordButtonState("idle");
  recordingHint.textContent = message;
  status.classList.remove("working");
  status.textContent = message;
}

stopVoiceButton.addEventListener("click", () => cancelVoiceSession());

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("读取录音失败，请重试。"));
    reader.onload = () => resolve(String(reader.result));
    reader.readAsDataURL(blob);
  });
}

let activeSpeech = null;
let chineseUtterance = null;
let uyghurAudio = null;
let uyghurAudioUrl = null;
let uyghurSpeechController = null;
let speechSessionId = 0;

function setSpeakButtonState(button, playing, language) {
  const idleLabel = `朗读${language}回答`;
  const activeLabel = `停止${language}朗读`;
  button.classList.toggle("is-speaking", playing);
  button.setAttribute("aria-pressed", String(playing));
  button.setAttribute("aria-label", playing ? activeLabel : idleLabel);
  button.title = playing ? activeLabel : idleLabel;
}

function stopAllSpeech(message = "") {
  speechSessionId += 1;
  activeSpeech = null;
  chineseUtterance = null;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  uyghurSpeechController?.abort();
  uyghurSpeechController = null;
  if (uyghurAudio) {
    uyghurAudio.pause();
    uyghurAudio.currentTime = 0;
    uyghurAudio = null;
  }
  if (uyghurAudioUrl) {
    URL.revokeObjectURL(uyghurAudioUrl);
    uyghurAudioUrl = null;
  }
  setSpeakButtonState(speakChineseButton, false, "中文");
  setSpeakButtonState(speakUyghurButton, false, "维吾尔语");
  speakChineseButton.disabled = false;
  speakUyghurButton.disabled = false;
  if (message) status.textContent = message;
}

function speakChineseAnswer(text) {
  const spokenText = text.trim();
  if (!spokenText) return;
  if (activeSpeech === "chinese") {
    stopAllSpeech("已停止中文朗读。再次点击将从头播放。");
    return;
  }
  if (!("speechSynthesis" in window) || !window.SpeechSynthesisUtterance) {
    status.textContent = "当前浏览器不支持语音朗读。";
    return;
  }

  stopAllSpeech();
  const sessionId = ++speechSessionId;
  activeSpeech = "chinese";
  const voices = window.speechSynthesis.getVoices();
  const voice = voices.find((item) => item.lang.toLowerCase().startsWith("zh"));
  const utterance = new SpeechSynthesisUtterance(spokenText);
  chineseUtterance = utterance;
  utterance.lang = voice?.lang || "zh-CN";
  if (voice) utterance.voice = voice;
  const finish = () => {
    if (sessionId !== speechSessionId || activeSpeech !== "chinese") return;
    activeSpeech = null;
    chineseUtterance = null;
    setSpeakButtonState(speakChineseButton, false, "中文");
    status.textContent = "中文朗读完成。再次点击将从头播放。";
  };
  utterance.onend = finish;
  utterance.onerror = finish;
  setSpeakButtonState(speakChineseButton, true, "中文");
  status.textContent = "正在播放中文语音；再次点击喇叭可停止。";
  window.speechSynthesis.speak(utterance);
}

speakChineseButton.addEventListener("click", () => {
  speakChineseAnswer(uyghurAnswerZh.textContent);
});

speakUyghurButton.addEventListener("click", async () => {
  const text = uyghurAnswerUg.textContent.trim();
  if (!text) return;
  if (activeSpeech === "uyghur") {
    stopAllSpeech("已停止维吾尔语朗读。再次点击将从头生成并播放。");
    return;
  }

  stopAllSpeech();
  const sessionId = ++speechSessionId;
  activeSpeech = "uyghur";
  const controller = new AbortController();
  uyghurSpeechController = controller;
  setSpeakButtonState(speakUyghurButton, true, "维吾尔语");
  status.textContent = "正在生成维吾尔语语音…";
  status.classList.add("working");
  try {
    const response = await apiFetch("/api/synthesize-uyghur", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });
    if (sessionId !== speechSessionId || activeSpeech !== "uyghur") return;
    if (!response.ok) {
      const result = await readApiResponse(response, "维语语音合成");
      throw new Error(result.error || "维语语音生成失败，请稍后重试。");
    }
    const audioBlob = await response.blob();
    if (!audioBlob.size) throw new Error("讯飞没有返回语音，请重试。");
    if (uyghurAudioUrl) URL.revokeObjectURL(uyghurAudioUrl);
    uyghurAudioUrl = URL.createObjectURL(audioBlob);
    uyghurAudio = new Audio(uyghurAudioUrl);
    uyghurAudio.addEventListener("ended", () => {
      if (sessionId !== speechSessionId || activeSpeech !== "uyghur") return;
      stopAllSpeech("维吾尔语朗读完成。再次点击将从头生成并播放。");
    }, { once: true });
    await uyghurAudio.play();
    if (sessionId === speechSessionId && activeSpeech === "uyghur") {
      status.textContent = "正在播放维吾尔语语音；再次点击喇叭可停止。";
    }
  } catch (error) {
    if (error.name !== "AbortError" && sessionId === speechSessionId) {
      stopAllSpeech();
      status.textContent = error.message || "维语语音生成失败，请稍后重试。";
    }
  } finally {
    status.classList.remove("working");
    if (uyghurSpeechController === controller) uyghurSpeechController = null;
  }
});

async function finishVoiceRecording(sessionId, recorder) {
  if (sessionId !== voiceSessionId) return;
  const elapsed = ((performance.now() - recordingStartedAt) / 1000).toFixed(1);
  const blob = new Blob(audioChunks, { type: recorder?.mimeType || "application/octet-stream" });
  audioChunks = [];
  stopMicrophoneTracks();
  if (!blob.size) {
    recordingHint.textContent = "没有录到声音，请按住按钮再说一次。";
    return;
  }
  if (blob.size > MAX_RECORDING_BYTES) {
    status.textContent = "录音超过 8 MB，请缩短后重试。";
    recordingHint.textContent = "按住按钮开始录音，松开后识别";
    return;
  }

  stopAllSpeech();
  transcriptionBusy = true;
  setRecordButtonState("busy");
  status.textContent = "正在识别维语、校正农牧词汇并请求双语回答…";
  status.classList.add("working");
  transcriptionCard.hidden = true;
  const controller = new AbortController();
  activeVoiceRequestController = controller;
  const uiSession = conversationUiSession;
  const requestTimer = window.setTimeout(() => controller.abort(), 210_000);
  try {
    const id = await ensureConversation();
    const dataUrl = await blobToDataUrl(blob);
    if (sessionId !== voiceSessionId) return;
    const base64 = dataUrl.split(",", 2)[1] || "";
    const containerMime = (blob.type || "audio/webm").split(";", 1)[0];
    if (!base64 || !["audio/webm", "audio/ogg", "audio/mp4"].includes(containerMime)) {
      throw new Error("浏览器生成了不支持的录音格式，请更新 Edge 或 Chrome 后重试。");
    }
    const normalizedDataUrl = `data:${containerMime};base64,${base64}`;
    const response = await apiFetch("/api/transcribe-uyghur-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audio: normalizedDataUrl, conversation_id: id }),
      signal: controller.signal,
    });
    if (sessionId !== voiceSessionId) return;
    if (uiSession !== conversationUiSession) return;
    if (!response.ok || !(response.headers.get("content-type") || "").includes("text/event-stream")) {
      const result = await readApiResponse(response, "维语问答");
      throw new Error(result.error || "语音问答未能启动流式响应，请重启本地服务后重试。");
    }

    const result = await consumeBilingualStream(response, {
      endpointName: "维语语音问答",
      onTranscript: (eventData) => {
        recordingHint.textContent = `识别完成 · 录音 ${elapsed} 秒 · 模型推理 ${eventData.inference_seconds} 秒`;
        status.textContent = "维语已识别并校正，腾讯正在翻译中文问题…";
      },
    });
    if (sessionId !== voiceSessionId) return;
    await refreshCurrentConversation();
    if (typeof result.question_zh === "string" && result.question_zh.trim()) {
      typedUyghurQuestionZh.textContent = result.question_zh;
      typedUyghurUnderstanding.hidden = false;
    }
    status.textContent = result.translation_failed
      ? "中文回答已完成，但维文翻译失败；中文结果已保留。"
      : "双语回答已完成；点击对应喇叭才会朗读。";
    uyghurAnswerCard.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (sessionId !== voiceSessionId) return;
    if (uiSession !== conversationUiSession) return;
    refreshCurrentConversation(false).catch(() => {});
    status.textContent = error.name === "AbortError" ? "等待神农生成双语回答超时，请稍后重试。" : (error.message || "请求失败，请稍后重试。");
    recordingHint.textContent = "识别失败。确认本机网页服务仍在运行后重试。";
  } finally {
    window.clearTimeout(requestTimer);
    if (activeVoiceRequestController === controller) activeVoiceRequestController = null;
    if (sessionId === voiceSessionId) {
      status.classList.remove("working");
      transcriptionBusy = false;
      setRecordButtonState("idle");
    }
  }
}

recordButton.addEventListener("pointerdown", (event) => {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  event.preventDefault();
  activePointerId = event.pointerId;
  recordButton.setPointerCapture?.(event.pointerId);
  beginVoiceRecording();
});
recordButton.addEventListener("pointerup", (event) => {
  if (activePointerId !== event.pointerId) return;
  activePointerId = null;
  stopVoiceRecording();
});
recordButton.addEventListener("pointercancel", () => { activePointerId = null; stopVoiceRecording(); });
recordButton.addEventListener("lostpointercapture", () => { activePointerId = null; stopVoiceRecording(); });
window.addEventListener("blur", () => stopVoiceRecording());
document.addEventListener("visibilitychange", () => { if (document.hidden) stopVoiceRecording(); });
window.addEventListener("beforeunload", () => {
  wantsRecording = false;
  recording = false;
  window.clearTimeout(recordingLimitTimer);
  if (mediaRecorder?.state === "recording") mediaRecorder.stop();
  stopMicrophoneTracks();
});
recordButton.addEventListener("keydown", (event) => {
  if ((event.code === "Space" || event.code === "Enter") && !event.repeat) {
    event.preventDefault();
    beginVoiceRecording();
  }
});
recordButton.addEventListener("keyup", (event) => {
  if (event.code === "Space" || event.code === "Enter") {
    event.preventDefault();
    stopVoiceRecording();
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = question.value.trim();
  if (!value) {
    status.textContent = "请先输入中文问题。";
    question.focus();
    return;
  }

  stopAllSpeech();
  submitButton.disabled = true;
  submitButton.textContent = "正在获取回答…";
  status.textContent = "正在等待神农回答，请稍候。";
  status.classList.add("working");
  answerCard.hidden = true;
  uyghurAnswerCard.hidden = true;
  answer.replaceChildren();
  uyghurAnswerZh.replaceChildren();
  uyghurAnswerUg.replaceChildren();

  const controller = new AbortController();
  activeTextController = controller;
  const uiSession = conversationUiSession;
  try {
    const id = await ensureConversation();
    const response = await apiFetch("/api/ask-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: value, conversation_id: id,
                             input_kind: question.dataset.fromVoice === "true" ? "chinese_voice" : "text" }),
      signal: controller.signal,
    });
    const result = await consumeBilingualStream(response, { endpointName: "中文双语问答" });
    if (uiSession !== conversationUiSession) return;
    await refreshCurrentConversation();
    question.value = "";
    question.dispatchEvent(new Event("input", { bubbles: true }));
    delete question.dataset.fromVoice;
    status.textContent = result.translation_failed
      ? "中文回答已完成，但维文翻译失败；中文结果已保留。"
      : "双语回答已完成；点击对应喇叭才会朗读。";
    uyghurAnswerCard.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (uiSession !== conversationUiSession) return;
    refreshCurrentConversation(false).catch(() => {});
    status.textContent = error.message || "请求失败，请稍后重试。";
  } finally {
    if (activeTextController === controller) activeTextController = null;
    status.classList.remove("working");
    submitButton.disabled = false;
    submitButton.innerHTML = '获取回答 <span aria-hidden="true">↗</span>';
  }
});

imageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = imageFile.files?.[0];
  if (!file || !["image/jpeg", "image/png"].includes(file.type) || file.size > 4 * 1024 * 1024) {
    status.textContent = "请选择不超过 4 MB 的 JPG 或 PNG 照片。";
    return;
  }

  stopAllSpeech();
  imageSubmitButton.disabled = true;
  imageSubmitButton.textContent = "正在识别…";
  status.textContent = "正在观察照片并询问神农，请稍候。";
  status.classList.add("working");
  observationCard.hidden = true;
  answerCard.hidden = true;
  uyghurAnswerCard.hidden = true;
  observation.textContent = "";
  answer.replaceChildren();
  uyghurAnswerZh.replaceChildren();
  uyghurAnswerUg.replaceChildren();

  const controller = new AbortController();
  activeImageController = controller;
  const uiSession = conversationUiSession;
  const timer = setTimeout(() => controller.abort(), 220000);
  try {
    const id = await ensureConversation();
    const image = await readFileAsDataURL(file);
    const response = await apiFetch("/api/ask-image-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image, question: imageQuestion.value.trim(), conversation_id: id }),
      signal: controller.signal,
    });
    const result = await consumeBilingualStream(response, { endpointName: "图片双语问答" });
    if (uiSession !== conversationUiSession) return;
    await refreshCurrentConversation();
    imageForm.reset();
    imagePreview.hidden = true;
    imagePreview.removeAttribute("src");
    status.textContent = result.translation_failed
      ? "图片观察和中文回答已完成，但维文翻译失败。"
      : "图片观察和双语回答已完成。";
    observationCard.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (uiSession !== conversationUiSession) return;
    refreshCurrentConversation(false).catch(() => {});
    status.textContent = error.name === "AbortError" ? "处理超时，请稍后重试。" : (error.message || "请求失败，请稍后重试。");
  } finally {
    clearTimeout(timer);
    if (activeImageController === controller) activeImageController = null;
    status.classList.remove("working");
    imageSubmitButton.disabled = false;
    imageSubmitButton.innerHTML = '识别并提问 <span aria-hidden="true">↗</span>';
  }
});

// One accessible composer toolbar delegates to the existing input pipelines.
let composerKind = "text";
let composerLanguage = localStorage.getItem("shennong_ui_language") === "ug" ? "ug" : "zh";
const composerSend = document.getElementById("composer-send");
const inputTabs = [...document.querySelectorAll("[data-input]")];
const languageButtons = [...document.querySelectorAll("[data-language]")];

function syncComposerMode(mode) {
  composerKind = mode === "image" ? "image" : ["audio", "chinese-audio"].includes(mode) ? "voice" : "text";
  if (mode !== "image") composerLanguage = ["audio", "uyghur-text"].includes(mode) ? "ug" : "zh";
  localStorage.setItem("shennong_ui_language", composerLanguage);
  UiLocale.apply(composerLanguage);
  inputTabs.forEach((button) => {
    const selected = button.dataset.input === composerKind;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  languageButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.language === composerLanguage)));
  imageQuestion.lang = composerLanguage === "ug" ? "ug" : "zh-CN";
  imageQuestion.dir = composerLanguage === "ug" ? "rtl" : "ltr";
  composerSend.hidden = composerKind === "voice";
  updateComposerBusy();
}

function composerMode() {
  if (composerKind === "image") return "image";
  if (composerKind === "voice") return composerLanguage === "ug" ? "audio" : "chinese-audio";
  return composerLanguage === "ug" ? "uyghur-text" : "text";
}

function updateComposerBusy() {
  const busy = submitButton.disabled || uyghurTextSubmit.disabled || imageSubmitButton.disabled || transcriptionBusy;
  stopAnswerButton.hidden = !busy;
  composerSend.disabled = busy;
  composerSend.classList.toggle("busy", busy);
  composerSend.innerHTML = busy ? '处理中 <span aria-hidden="true"></span>' : '发送 <span aria-hidden="true">↑</span>';
  inputTabs.forEach((button) => { button.disabled = busy; });
  languageButtons.forEach((button) => { button.disabled = busy; });
}

inputTabs.forEach((button) => button.addEventListener("click", () => {
  composerKind = button.dataset.input;
  selectMode(composerMode());
}));
languageButtons.forEach((button) => button.addEventListener("click", () => {
  composerLanguage = button.dataset.language;
  selectMode(composerMode(), true);
}));
composerSend.addEventListener("click", () => {
  const target = composerKind === "image" ? imageForm : composerLanguage === "ug" ? uyghurTextForm : form;
  target.requestSubmit();
});
const composerObserver = new MutationObserver(updateComposerBusy);
[submitButton, uyghurTextSubmit, imageSubmitButton, recordButton].forEach((button) => {
  composerObserver.observe(button, { attributes: true, attributeFilter: ["disabled"] });
});
const speakerIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 4 6 8H3v8h3l5 4V4Z"/><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/></svg>';
speakChineseButton.innerHTML = speakerIcon;
speakUyghurButton.innerHTML = speakerIcon;

function bootLocalPage() {
  clearActiveAnswer();
  composerLanguage = localStorage.getItem("shennong_ui_language") === "ug" ? "ug" : "zh";
  selectMode(composerLanguage === "ug" ? "uyghur-text" : "text");
  const savedConversationId = localStorage.getItem(selectionKey());
  if (savedConversationId && /^[0-9a-f]{32}$/.test(savedConversationId)) {
    openConversation(savedConversationId).catch(() => refreshHistoryList());
  } else {
    refreshHistoryList().catch((error) => { status.textContent = error.message; });
  }
}

bootLocalPage();
