(() => {
  const chatFab = document.getElementById("chatFab");
  const chatDrawer = document.getElementById("chatDrawer");
  const chatOverlay = document.getElementById("chatOverlay");
  const chatClose = document.getElementById("chatClose");
  const openTriggers = [
    document.getElementById("navChatBtn"),
    document.getElementById("heroChatBtn"),
    document.getElementById("faqChatBtn"),
    chatFab,
  ].filter(Boolean);

  function openChat() {
    chatDrawer.hidden = false;
    chatOverlay.hidden = false;
    chatFab.hidden = true;
    document.getElementById("messageInput")?.focus();
  }

  function closeChat() {
    chatDrawer.hidden = true;
    chatOverlay.hidden = true;
    chatFab.hidden = false;
  }

  openTriggers.forEach((btn) => btn.addEventListener("click", openChat));
  chatClose?.addEventListener("click", closeChat);
  chatOverlay?.addEventListener("click", closeChat);

  const chatLog = document.getElementById("chatLog");
  const chatForm = document.getElementById("chatForm");
  const messageInput = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");
  const statusLine = document.getElementById("statusLine");
  const modelInput = document.getElementById("modelInput");
  const tempInput = document.getElementById("tempInput");
  const resetBtn = document.getElementById("resetBtn");

  // Balasan chatbot ditampilkan lewat innerHTML (bukan textContent) supaya
  // gambar (barcode QRIS) dan link (WhatsApp) bisa tampil/diklik langsung.
  // escapeHtml() WAJIB dijalankan dulu sebelum linkify supaya teks dari
  // user/bot tidak bisa menyuntik HTML/script (XSS) — baru setelah itu
  // markdown gambar & URL polos diubah jadi tag <img>/<a>.
  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function linkify(text) {
    const escaped = escapeHtml(text);

    // Gambar (mis. barcode/QRIS): ![alt](/path/gambar.png). Diproses lebih
    // dulu dan ditaruh sementara di array `images`, digantikan token unik,
    // supaya URL di dalam tanda kurungnya TIDAK ikut dobel di-linkify oleh
    // urlPattern di bawah, lalu dikembalikan lagi di akhir.
    const images = [];
    const imgPattern = /!\[([^\]]*)\]\((\/[^\s)]+)\)/g;
    const withImgTokens = escaped.replace(imgPattern, (_match, alt, src) => {
      const token = `\u0000IMG${images.length}\u0000`;
      images.push(
        `<img src="${src}" alt="${alt}" class="msg__img" loading="lazy">`,
      );
      return token;
    });

    const urlPattern = /(https?:\/\/[^\s<]+)/g;
    const withLinks = withImgTokens.replace(urlPattern, (url) => {
      // jangan ikut-ikutkan tanda baca penutup kalimat (. , ) ! ?) ke dalam link
      const trailingMatch = url.match(/[).,!?]+$/);
      let clean = url;
      let trailing = "";
      if (trailingMatch) {
        trailing = trailingMatch[0];
        clean = url.slice(0, -trailing.length);
      }
      return `<a href="${clean}" target="_blank" rel="noopener noreferrer">${clean}</a>${trailing}`;
    });

    const withBreaks = withLinks.replace(/\n/g, "<br>");
    return withBreaks.replace(
      /\u0000IMG(\d+)\u0000/g,
      (_m, i) => images[Number(i)],
    );
  }

  const STORAGE_KEY = "sewa_jas_chat_history";
  let history = loadHistory(); // [{role: 'user'|'assistant', content: '...'}]

  function loadHistory() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  function saveHistory() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
    } catch {
      /* localStorage tidak tersedia — percakapan tetap jalan, cuma tidak persist */
    }
  }

  function renderHistory() {
    chatLog.innerHTML = "";
    if (history.length === 0) {
      appendBubble("assistant", "Haiii, selamat datang! 👋 Mau tanya soal ukuran, warna, harga, atau cara sewa? Langsung tulis aja di bawah.", false);
      return;
    }
    for (const m of history) {
      appendBubble(m.role, m.content, false);
    }
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function appendBubble(role, text, animate = true) {
    const wrap = document.createElement("div");
    wrap.className = `msg msg--${role}`;
    const bubble = document.createElement("div");
    bubble.className = "msg__bubble";
    bubble.innerHTML = linkify(text);
    wrap.appendChild(bubble);
    chatLog.appendChild(wrap);
    if (animate) chatLog.scrollTop = chatLog.scrollHeight;
    return bubble;
  }

  function autoResize() {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + "px";
  }
  messageInput.addEventListener("input", autoResize);

  resetBtn.addEventListener("click", () => {
    history = [];
    saveHistory();
    renderHistory();
    statusLine.textContent = "";
  });

  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = messageInput.value.trim();
    if (!text) return;

    messageInput.value = "";
    autoResize();
    sendBtn.disabled = true;

    appendBubble("user", text);
    history.push({ role: "user", content: text });
    saveHistory();

    const assistantBubble = appendBubble("assistant", "", true);
    assistantBubble.classList.add("typing");
    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          history: history.slice(0, -1), // riwayat sebelum pesan ini (server akan tambahkan pesan user)
          model: modelInput.value.trim() || undefined,
          temperature: parseFloat(tempInput.value),
        }),
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let fullText = "";   // teks lengkap yang sudah diterima dari server
      let shownText = "";  // teks yang sudah ditampilkan ke user, dikit demi dikit
      let streamDone = false;

      const CHAR_DELAY_MS = 20; // makin besar angkanya, makin pelan efek ketiknya

      // Loop terpisah buat nampilin teks pelan-pelan, gak ikut kecepatan
      // network/Ollama — jadi efek ketiknya smooth & konsisten tiap kali,
      // gak kepengaruh chunk gede/kecil yang dateng dari server.
      async function revealLoop() {
        while (!streamDone || shownText.length < fullText.length) {
          if (shownText.length < fullText.length) {
            shownText += fullText[shownText.length];
            assistantBubble.innerHTML = linkify(shownText);
            chatLog.scrollTop = chatLog.scrollHeight;
            await new Promise((r) => setTimeout(r, CHAR_DELAY_MS));
          } else {
            await new Promise((r) => setTimeout(r, 30)); // nunggu chunk baru dateng
          }
        }
      }
      const revealPromise = revealLoop();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        fullText += decoder.decode(value, { stream: true });
      }
      streamDone = true;
      await revealPromise; // tunggu semua karakter selesai ditampilin

      assistantBubble.classList.remove("typing");
      history.push({ role: "assistant", content: fullText });
      saveHistory();
      statusLine.textContent = "";
    } catch (err) {
      assistantBubble.classList.remove("typing");
      assistantBubble.textContent =
        "⚠️ Gagal terhubung ke server. Pastikan aplikasi Flask (python app.py) dan Ollama sama-sama sedang berjalan.";
      statusLine.textContent = "Terjadi kesalahan koneksi.";
    } finally {
      sendBtn.disabled = false;
      messageInput.focus();
    }
  });

  // Kirim dengan Enter, baris baru dengan Shift+Enter
  messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.requestSubmit();
    }
  });

  renderHistory();
})();