const chatToggle = document.getElementById("chatToggle");
const chatWindow = document.getElementById("chatWindow");
const chatClose = document.getElementById("chatClose");
const chatSend = document.getElementById("chatSend");
const chatInput = document.getElementById("chatInput");
const chatMessages = document.getElementById("chatMessages");

chatToggle.addEventListener("click", () => {
    chatWindow.style.display = "block";
    chatToggle.style.display = "none";
});

chatClose.addEventListener("click", () => {
    chatWindow.style.display = "none";
    chatToggle.style.display = "block";
});

function addMessage(text, className, isHtml = false) {
    const div = document.createElement("div");
    div.className = className;

    if (isHtml) {
        div.innerHTML = text;
    } else {
        div.textContent = text;
    }

    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    addMessage(message, "userMsg");
    chatInput.value = "";

    addMessage("Thinking...", "botMsg");
    const thinkingMsg = chatMessages.lastChild;

    try {
        const response = await fetch("/chatbot", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ message })
        });

        const data = await response.json();

        thinkingMsg.innerHTML = data.reply || "Sorry, I could not answer that.";
    } catch (error) {
        thinkingMsg.textContent = "Sorry, the chatbot is not reachable right now.";
    }
}

chatSend.addEventListener("click", sendMessage);

chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        sendMessage();
    }
});

document.querySelectorAll(".promptBtn").forEach((btn) => {
    btn.addEventListener("click", () => {
        const prompt = btn.dataset.prompt;

        if (prompt === "Help me understand the blog titled ") {
            chatInput.value = prompt;
            chatInput.focus();
        } else {
            chatInput.value = prompt;
            sendMessage();
        }
    });
});