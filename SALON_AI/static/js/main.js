/* Shared, safe presentation helpers for every AI assistant widget tab. */
(function () {
  const escapeHtml = (value) => String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');

  // Small Markdown subset used by Gemini responses; all content is escaped first.
  const renderMarkdown = (value) => {
    const lines = escapeHtml(value).split(/\r?\n/);
    let html = '', inList = false;
    const inline = (line) => line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>');
    lines.forEach(line => {
      const heading = line.match(/^#{1,3}\s+(.+)/);
      const bullet = line.match(/^\s*[-*]\s+(.+)/);
      if (bullet) { if (!inList) { html += '<ul class="ai-markdown-list">'; inList = true; } html += `<li>${inline(bullet[1])}</li>`; return; }
      if (inList) { html += '</ul>'; inList = false; }
      if (heading) html += `<h6 class="ai-markdown-heading">${inline(heading[1])}</h6>`;
      else if (line.trim()) html += `<p class="mb-2">${inline(line)}</p>`;
    });
    if (inList) html += '</ul>';
    return html || '<span class="text-secondary">Chưa có nội dung.</span>';
  };
  window.renderAiMarkdown = renderMarkdown;

  window.renderAiRecommendation = function (payload) {
    let data = payload;
    if (typeof data === 'string') { try { data = JSON.parse(data); } catch (_) { return `<div class="ai-plain-text">${escapeHtml(data)}</div>`; } }
    if (!data || typeof data !== 'object') return `<div class="ai-plain-text">${escapeHtml(data || '')}</div>`;
    let recommendations = data.recommended_services;
    if (typeof recommendations === 'string') { try { recommendations = JSON.parse(recommendations); } catch (_) { recommendations = recommendations.split(/[,\n]+/); } }
    if (!Array.isArray(recommendations)) recommendations = recommendations ? [recommendations] : [];
    if (data.reply && !data.reason && !recommendations.length) return `<div class="ai-plain-text">${renderMarkdown(data.reply)}</div>`;
    const reason = data.reason || data.analysis || '';
    const services = recommendations.filter(Boolean).map(item => { const label = typeof item === 'object' ? (item.name || item.service_name || JSON.stringify(item)) : item; return `<div class="ai-recommendation-item"><span class="ai-recommendation-check">✓</span><span>${escapeHtml(label)}</span></div>`; }).join('');
    if (!reason && !services) return `<div class="ai-plain-text">${escapeHtml(JSON.stringify(data))}</div>`;
    return `<div class="ai-recommendation-result">${reason ? `<div class="ai-recommendation-reason"><strong>💡 Phân tích AI:</strong><div>${renderMarkdown(reason)}</div></div>` : ''}${services ? `<div class="ai-recommendation-list"><div class="small fw-semibold text-secondary mb-2">Dịch vụ gợi ý</div>${services}</div>` : ''}${data.warning ? `<div class="small text-secondary mt-2">${renderMarkdown(data.warning)}</div>` : ''}</div>`;
  };

  window.renderAiMessage = function (value) {
    const text = typeof value === 'object' ? (value.reply || value.message || '') : String(value ?? '');
    const chunks = text.split(/(?=^#{1,3}\s*(?:Mẫu|Mau)\s*\d+)/gim).map(item => item.trim()).filter(Boolean);
    const samples = chunks.length > 1 ? chunks : [text];
    window.__aiMessageCopies = samples.map(sample => sample.replace(/^#{1,3}\s*(?:Mẫu|Mau)\s*\d+\s*/i, '').trim());
    return samples.map((sample, index) => `<article class="ai-message-card"><div class="d-flex justify-content-between align-items-center mb-2"><strong>Mẫu ${index + 1}</strong><button type="button" class="btn btn-sm btn-outline-secondary ai-copy-message" data-copy-index="${index}">📋 Sao chép nội dung</button></div><div class="ai-message-content">${renderMarkdown(window.__aiMessageCopies[index])}</div></article>`).join('');
  };

  window.renderAiSummary = function (value) {
    const text = typeof value === 'object' ? (value.summary || value.reply || '') : String(value ?? '');
    return `<article class="ai-summary-card"><div class="fw-bold mb-2">Hồ sơ tóm tắt khách hàng</div><div class="ai-summary-content">${renderMarkdown(text)}</div></article>`;
  };

  document.addEventListener('click', event => {
    const button = event.target.closest('.ai-copy-message');
    if (!button) return;
    const text = (window.__aiMessageCopies || [])[Number(button.dataset.copyIndex)] || '';
    navigator.clipboard?.writeText(text).then(() => { const old = button.innerHTML; button.innerHTML = '✓ Đã sao chép'; setTimeout(() => { button.innerHTML = old; }, 1400); }).catch(() => { button.innerHTML = 'Không thể sao chép'; });
  });

  // The widget keeps its existing chat transport; only upgrade the bubble
  // presentation after each message is appended.
  const upgradeChatBubbles = () => document.querySelectorAll('#admin-ai-chat-log .admin-ai-msg').forEach(node => {
    if (node.dataset.markdownReady === '1') return;
    const raw = node.textContent || '';
    node.innerHTML = renderMarkdown(raw);
    node.dataset.markdownReady = '1';
  });
  const chatLog = document.getElementById('admin-ai-chat-log');
  if (chatLog) { upgradeChatBubbles(); new MutationObserver(upgradeChatBubbles).observe(chatLog, { childList: true }); }

  const installThinkingState = (form, input, button, messages, bubbleClass) => {
    if (!form || !input || !button || !messages || form.dataset.thinkingReady) return;
    form.dataset.thinkingReady = '1';
    let active = false, timeout;
    const unlock = () => { active = false; clearTimeout(timeout); input.disabled = false; button.disabled = false; messages.querySelector('#ai-thinking-bubble')?.remove(); input.focus(); };
    const showThinking = () => {
      messages.querySelector('#ai-thinking-bubble')?.remove();
      const bubble = document.createElement('div');
      bubble.id = 'ai-thinking-bubble';
      bubble.className = `${bubbleClass} ai-thinking-bubble`;
      bubble.innerHTML = '<span>🤖 Trợ lý đang suy nghĩ</span><span class="spinner-border spinner-border-sm" role="status" aria-label="Đang suy nghĩ"></span>';
      messages.appendChild(bubble); messages.scrollTo({top: messages.scrollHeight, behavior: 'smooth'});
      active = true; input.disabled = true; button.disabled = true;
      timeout = setTimeout(() => { if (!active) return; unlock(); const error = document.createElement('div'); error.className = bubbleClass; error.textContent = '⚠️ Trợ lý AI đang bận hoặc phản hồi chậm, vui lòng thử lại câu hỏi nhé!'; messages.appendChild(error); messages.scrollTop = messages.scrollHeight; }, 35000);
    };
    form.addEventListener('submit', showThinking, true);
    new MutationObserver(records => { if (!active) return; const addedAssistant = records.flatMap(record => [...record.addedNodes]).some(node => node.nodeType === 1 && node.id !== 'ai-thinking-bubble' && (node.classList.contains('assistant') || node.classList.contains('admin-ai-msg') || node.classList.contains('bot'))); if (addedAssistant) unlock(); }).observe(messages, {childList: true});
  };
  window.installAiThinkingState = installThinkingState;
  document.addEventListener('DOMContentLoaded', () => {
    installThinkingState(document.getElementById('admin-ai-chat-form'), document.getElementById('admin-ai-chat-input'), document.querySelector('#admin-ai-chat-form button'), document.getElementById('admin-ai-chat-log'), 'admin-ai-msg assistant');
    installThinkingState(document.getElementById('salon-chat-form'), document.getElementById('salon-chat-input'), document.getElementById('salon-chat-send'), document.getElementById('salon-chat-messages'), 'salon-chat-message assistant');
  });
})();
