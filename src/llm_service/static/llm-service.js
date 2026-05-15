const chatForm = document.getElementById("chat-form");
const sendButton = document.getElementById("send");
const micButton = document.getElementById("mic");
const promptInput = document.getElementById("prompt");
const statusNode = document.getElementById("status");
const chatFeed = document.getElementById("chat-feed");
const chatHeader = document.querySelector(".chat-header");
const composerShell = document.querySelector(".composer-shell");
const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

let recognition = null;
let isListening = false;
let prefersNativeSpeech = false;

function setStatus(message, state) {
  statusNode.textContent = message;
  statusNode.dataset.state = state;
}

function autoResizeTextarea() {
  promptInput.style.height = "auto";
  promptInput.style.height = `${Math.min(promptInput.scrollHeight, 180)}px`;
}

function updateMicButton() {
  if (!micButton) {
    return;
  }

  if (prefersNativeSpeech) {
    micButton.textContent = isListening ? "Listening..." : "Speak";
    micButton.disabled = false;
    micButton.dataset.state = isListening ? "listening" : "idle";
    return;
  }

  if (!SpeechRecognition) {
    micButton.textContent = "No Mic";
    micButton.disabled = true;
    micButton.dataset.state = "unsupported";
    return;
  }

  micButton.textContent = isListening ? "Listening..." : "Speak";
  micButton.dataset.state = isListening ? "listening" : "idle";
}

function scrollMessageToTop(row, behavior = "smooth") {
  if (!row) {
    return;
  }

  const headerHeight = chatHeader?.offsetHeight ?? 0;
  const topGap = 12;
  const targetTop =
    window.scrollY + row.getBoundingClientRect().top - headerHeight - topGap;

  window.scrollTo({
    top: Math.max(0, targetTop),
    behavior,
  });
}

function keepReplyVisible(userRow, assistantRow, behavior = "smooth") {
  if (!userRow || !assistantRow) {
    return;
  }

  scrollMessageToTop(userRow, behavior);

  requestAnimationFrame(() => {
    const composerHeight = composerShell?.offsetHeight ?? 0;
    const bottomGap = 12;
    const assistantBottom = assistantRow.getBoundingClientRect().bottom;
    const visibleBottom = window.innerHeight - composerHeight - bottomGap;

    if (assistantBottom > visibleBottom) {
      window.scrollBy({
        top: assistantBottom - visibleBottom,
        behavior,
      });
    }
  });
}

function appendMessage(role, text) {
  const row = document.createElement("article");
  row.className = `message-row ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  if (role === "user") {
    avatar.textContent = "YOU";
  } else {
    avatar.classList.add("assistant-avatar");
    const image = document.createElement("img");
    image.src = "/img/master-spline.png";
    image.alt = "Assistant avatar";
    avatar.appendChild(image);
  }

  const group = document.createElement("div");
  group.className = "bubble-group";

  const speaker = document.createElement("p");
  speaker.className = "speaker";
  speaker.textContent = role === "user" ? "You" : "Assistant";

  const bubble = document.createElement("div");
  bubble.className = `message-bubble ${role === "user" ? "user-bubble" : "assistant-bubble"}`;
  bubble.textContent = text;

  group.appendChild(speaker);
  group.appendChild(bubble);
  row.appendChild(avatar);
  row.appendChild(group);
  chatFeed.appendChild(row);

  return { row, bubble };
}

async function sendPrompt() {
  const prompt = promptInput.value.trim();
  if (!prompt) {
    setStatus("Enter a message first.", "error");
    promptInput.focus();
    return;
  }

  const { row: userRow } = appendMessage("user", prompt);
  scrollMessageToTop(userRow);
  promptInput.value = "";
  autoResizeTextarea();
  sendButton.disabled = true;
  setStatus("Thinking...", "working");

  const {
    row: assistantRow,
    bubble: assistantBubble,
  } = appendMessage("assistant", "Working...");
  keepReplyVisible(userRow, assistantRow);

  try {
    const response = await fetch("/api/prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Request failed");
    }

    assistantBubble.textContent = data.reply || "";
    keepReplyVisible(userRow, assistantRow);
    setStatus("Ready", "success");
  } catch (error) {
    assistantBubble.textContent = error.message || String(error);
    keepReplyVisible(userRow, assistantRow);
    setStatus("Request failed", "error");
  } finally {
    sendButton.disabled = false;
    promptInput.focus();
  }
}

function requestNativeSpeechToText() {
  if (typeof Android === "undefined" || typeof Android.sendJsonData !== "function") {
    return false;
  }

  isListening = true;
  updateMicButton();
  setStatus("Listening...", "working");
  Android.sendJsonData("speech_to_text", JSON.stringify({ action: "start" }));
  return true;
}

function setupSpeechRecognition() {
  if (!micButton) {
    return;
  }

  if (typeof Android !== "undefined" && typeof Android.sendJsonData === "function") {
    prefersNativeSpeech = true;
    micButton.addEventListener("click", () => {
      if (isListening) {
        return;
      }

      promptInput.focus();
      requestNativeSpeechToText();
    });
    updateMicButton();
    return;
  }

  if (!SpeechRecognition) {
    updateMicButton();
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = "it-IT";
  recognition.continuous = false;
  recognition.interimResults = true;

  recognition.onstart = () => {
    isListening = true;
    updateMicButton();
    setStatus("Listening...", "working");
  };

  recognition.onresult = (event) => {
    let transcript = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      transcript += event.results[i][0].transcript;
    }

    promptInput.value = transcript.trim();
    autoResizeTextarea();
  };

  recognition.onend = () => {
    isListening = false;
    updateMicButton();
    setStatus("Ready", "success");
    promptInput.focus();
  };

  recognition.onerror = (event) => {
    isListening = false;
    updateMicButton();
    setStatus(`Mic error: ${event.error}`, "error");
  };

  micButton.addEventListener("click", () => {
    if (isListening) {
      recognition.stop();
      return;
    }

    promptInput.focus();
    recognition.start();
  });

  updateMicButton();
}

window.setPromptFromNative = function (text) {
  isListening = false;
  promptInput.value = text || "";
  autoResizeTextarea();
  promptInput.focus();
  updateMicButton();
  setStatus("Ready", "success");
};

window.onNativeSpeechError = function (message) {
  isListening = false;
  updateMicButton();
  setStatus(message || "Mic error", "error");
};

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendPrompt();
});

promptInput.addEventListener("input", autoResizeTextarea);
promptInput.addEventListener("keydown", async (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    await sendPrompt();
  }
});

autoResizeTextarea();
setupSpeechRecognition();
