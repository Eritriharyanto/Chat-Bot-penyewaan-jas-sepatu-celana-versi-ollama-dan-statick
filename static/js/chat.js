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

  // Data toko (dikirim dari server lewat hidden input di template) buat
  // bikin link WA / Maps yang bisa diklik & gambar QRIS di dalam chat.
  const waLink = document.getElementById("waLinkInput")?.value || "";
  const mapsLink = document.getElementById("mapsLinkInput")?.value || "";
  const qrisImg = document.getElementById("qrisImgInput")?.value || "";
  const alamatText = document.getElementById("alamatTextInput")?.value || "";

  const STORAGE_KEY = "sewa_jas_chat_history";
  let history = loadHistory(); // [{role: 'user'|'assistant', content: '...', action?: 'qris'|'alamat'|'kontak'}]

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

  function escapeHtml(str) {
    return str.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // Ubah teks jawaban asisten jadi HTML yang aman, sambil mengubah:
  // - alamat toko  -> link Google Maps yang bisa diklik
  // - nomor WA/HP  -> link wa.me yang bisa diklik
  function linkifyText(rawText) {
    let escaped = escapeHtml(rawText);

    if (alamatText && mapsLink) {
      const escapedAlamat = escapeHtml(alamatText);
      if (escaped.includes(escapedAlamat)) {
        escaped = escaped.split(escapedAlamat).join(
          `<a href="${mapsLink}" target="_blank" rel="noopener" class="chat-link chat-link--map"> ${escapedAlamat}</a>`
        );
      }
    }

    // Cocokkan format nomor HP/WA Indonesia: 08xx-xxxx-xxxx, 08xxxxxxxxxx, +62 8xx..., 628xx...
    const phoneRegex = /(?:\+62|62|0)8[0-9](?:[\s-]?[0-9]){7,10}/g;
    escaped = escaped.replace(phoneRegex, (match) => {
      let digits = match.replace(/\D/g, "");
      if (digits.startsWith("0")) digits = "62" + digits.slice(1);
      else if (!digits.startsWith("62")) digits = "62" + digits;
      return `<a href="https://wa.me/${digits}" target="_blank" rel="noopener" class="chat-link chat-link--wa"> ${match}</a>`;
    });

    return escaped;
  }

  // Tempel elemen interaktif tambahan di bawah bubble asisten sesuai
  // jenis pertanyaannya: gambar QRIS + tombol konfirmasi WA, tombol buka
  // Maps, atau tombol chat WA.
  function appendActionExtras(wrap, action) {
    if (!action || !wrap) return;
    const extras = document.createElement("div");
    extras.className = "msg__extras";

    if (action === "qris" && qrisImg) {
      extras.innerHTML = `
        <img src="${qrisImg}" alt="QRIS Pembayaran" class="qris-img" loading="lazy">
        <a href="${waLink}" target="_blank" rel="noopener" class="chat-action-btn chat-action-btn--wa">✅ Sudah scan &amp; bayar? Konfirmasi via WhatsApp</a>
      `;
    } else if (action === "alamat" && mapsLink) {
      extras.innerHTML = `<a href="${mapsLink}" target="_blank" rel="noopener" class="chat-action-btn">📍 Buka lokasi di Google Maps</a>`;
    } else if (action === "kontak" && waLink) {
      extras.innerHTML = `<a href="${waLink}" target="_blank" rel="noopener" class="chat-action-btn chat-action-btn--wa">💬 Chat Admin via WhatsApp</a>`;
    } else {
      return;
    }
    wrap.appendChild(extras);
  }

  // Selesaikan bubble asisten: ganti teks polos jadi HTML dengan link yang
  // bisa diklik, lalu tempel elemen tambahan (QRIS/Maps/WA) kalau ada.
  function finalizeAssistantMessage(bubble, text, action) {
    bubble.innerHTML = linkifyText(text);
    appendActionExtras(bubble.parentElement, action);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function renderHistory() {
    chatLog.innerHTML = "";
    if (history.length === 0) {
      appendBubble("assistant", "Haiii, selamat datang! 👋 Mau tanya soal ukuran, warna, harga, atau cara sewa? Langsung tulis aja di bawah.", false);
      return;
    }
    for (const m of history) {
      const bubble = appendBubble(m.role, m.content, false);
      if (m.role === "assistant") {
        finalizeAssistantMessage(bubble, m.content, m.action || "");
      }
    }
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function appendBubble(role, text, animate = true) {
    const wrap = document.createElement("div");
    wrap.className = `msg msg--${role}`;
    const col = document.createElement("div");
    col.className = "msg__col";
    const bubble = document.createElement("div");
    bubble.className = "msg__bubble";
    bubble.textContent = text;
    col.appendChild(bubble);
    wrap.appendChild(col);
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
    let chatAction = "";
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

      // Header dari server yang bilang apakah jawaban ini perlu ditempeli
      // gambar QRIS, tombol Maps, atau tombol WA.
      chatAction = resp.headers.get("X-Chat-Action") || "";

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
            assistantBubble.textContent = shownText;
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
      finalizeAssistantMessage(assistantBubble, fullText, chatAction);
      history.push({ role: "assistant", content: fullText, action: chatAction });
      saveHistory();
      statusLine.textContent = "";
    } catch (err) {
      assistantBubble.classList.remove("typing");
      assistantBubble.textContent =
        "⚠️ Gagal terhubung ke server. Pastikan aplikasi Flask (python run.py) dan Ollama sama-sama sedang berjalan.";
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