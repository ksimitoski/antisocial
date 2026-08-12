// Theme Management (Light / Dark Mode)
document.addEventListener('DOMContentLoaded', () => {
  const savedTheme = localStorage.getItem('antisocial_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);
  updateThemeButtonUI(savedTheme);

  const themeBtn = document.getElementById('theme-toggle-btn');
  if (themeBtn) {
    themeBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('antisocial_theme', next);
      updateThemeButtonUI(next);
    });
  }

  // Mobile Hamburger Menu Toggle
  const mobileToggle = document.getElementById('mobile-menu-toggle');
  const navLinks = document.getElementById('nav-links');
  if (mobileToggle && navLinks) {
    mobileToggle.addEventListener('click', () => {
      mobileToggle.classList.toggle('active');
      navLinks.classList.toggle('open');
    });

    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
      if (!mobileToggle.contains(e.target) && !navLinks.contains(e.target)) {
        mobileToggle.classList.remove('active');
        navLinks.classList.remove('open');
      }
    });
  }

  checkNoticeDismissal();
  checkCookieConsent();
  updateUnreadMessagesBadge();
  setupGlobalFetchAuthHandler();
  setupActivityHeartbeat();
  setupNotificationPoller();
  loadUserTimezoneCache();

  updateOnlineStatuses();
  setInterval(updateOnlineStatuses, 10000);

  // Poll for unread messages badge every 30 seconds (except on the messages page, which has its own 5s polling loop)
  if (!document.body.classList.contains('messages-page') && window.location.pathname !== '/messages') {
    setInterval(() => {
      updateUnreadMessagesBadge();
    }, 30000);
  }
});

function setupActivityHeartbeat() {
  const token = document.body.getAttribute('data-token') || (typeof window.token !== 'undefined' ? window.token : null);
  if (!token) return;

  // Send activity heartbeat ping every 30 seconds (30,000ms)
  setInterval(async () => {
    try {
      await fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
    } catch (e) {}
  }, 30000);
}

async function updateOnlineStatuses() {
  const elements = document.querySelectorAll('.status-indicator[data-username], .status-text-badge[data-username]');
  if (!elements || elements.length === 0) return;

  const usernames = Array.from(new Set(
    Array.from(elements).map(el => el.getAttribute('data-username')).filter(Boolean)
  ));
  if (usernames.length === 0) return;

  try {
    const res = await fetch(`/api/users/online-statuses?usernames=${encodeURIComponent(usernames.join(','))}`);
    if (!res.ok) return;
    const data = await res.json();
    const statuses = data.statuses || {};

    elements.forEach(el => {
      const uname = el.getAttribute('data-username');
      if (!uname || !(uname in statuses)) return;

      const statusVal = (statuses[uname] || 'unknown').toLowerCase();
      let statusDotClass = 'unknown';
      let statusBadgeText = '❓ Unknown';

      if (statusVal === 'online') {
        statusDotClass = 'online';
        statusBadgeText = '🟢 Online';
      } else if (statusVal === 'offline') {
        statusDotClass = 'offline';
        statusBadgeText = '⚪ Offline';
      }

      if (el.classList.contains('status-indicator')) {
        el.className = `status-indicator ${statusDotClass}`;
        el.setAttribute('title', `Status: ${statusVal}`);
      } else if (el.classList.contains('status-text-badge')) {
        el.innerText = statusBadgeText;
      }
    });
  } catch (e) {}
}

let lastNotificationServerTime = localStorage.getItem('last_notification_server_time') || null;

function setupNotificationPoller() {
  const token = document.body.getAttribute('data-token') || (typeof window.token !== 'undefined' ? window.token : null);
  if (!token) return;

  setTimeout(pollBrowserNotifications, 3000);
  setInterval(pollBrowserNotifications, 15000);
}

async function pollBrowserNotifications() {
  const token = document.body.getAttribute('data-token') || (typeof window.token !== 'undefined' ? window.token : null);
  if (!token) return;

  try {
    let url = '/api/notifications/poll';
    if (lastNotificationServerTime) {
      url += `?since=${encodeURIComponent(lastNotificationServerTime)}`;
    }
    const res = await fetch(url, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) return;

    const data = await res.json();
    if (data.server_time) {
      lastNotificationServerTime = data.server_time;
      localStorage.setItem('last_notification_server_time', lastNotificationServerTime);
    }

    triggerInAppToastNotifications(data);
  } catch (e) {}
}

function triggerInAppToastNotifications(data) {
  const messages = data.notify_messages ? (data.messages || []) : [];
  const comments = data.notify_comments ? (data.comments || []) : [];
  const posts = data.posts || [];
  const mode = data.notification_mode || 'constant';
  const obscure = data.obscure_notification_content || false;

  const total = messages.length + comments.length + posts.length;
  if (total === 0) return;

  if (messages.length > 0 && typeof playIncomingMessageSound === 'function') {
    playIncomingMessageSound();
  }

  if (mode === 'limited') {
    let bodyText = `You have ${total} new notification${total > 1 ? 's' : ''} on Antisocial.`;
    if (messages.length > 0 && comments.length > 0) {
      bodyText = `You have ${messages.length} new message${messages.length > 1 ? 's' : ''} and ${comments.length} new comment${comments.length > 1 ? 's' : ''}.`;
    } else if (messages.length > 0) {
      bodyText = `You have ${messages.length} new message${messages.length > 1 ? 's' : ''}.`;
    } else if (comments.length > 0) {
      bodyText = `You have ${comments.length} new comment${comments.length > 1 ? 's' : ''} on your posts.`;
    } else if (posts.length > 0) {
      bodyText = `You have ${posts.length} new post${posts.length > 1 ? 's' : ''} from followed friends.`;
    }

    showToast(`🔔 Notifications: ${bodyText}`, 'info', 6000);
  } else {
    messages.forEach(m => {
      const senderName = m.sender_display_name || m.sender_username;
      let bodyText = 'Sent a message';
      if (obscure) {
        bodyText = 'New message received (content hidden for privacy)';
      } else if (m.content) {
        bodyText = m.content.length > 80 ? m.content.substring(0, 77) + '...' : m.content;
      }

      showToast(`💬 ${senderName}: ${bodyText}`, 'info', 6000);
    });

    comments.forEach(c => {
      const authorName = c.author_display_name || c.author_username;
      const isReply = c.is_reply || false;
      let bodyText = isReply ? `${authorName} replied to your comment` : `${authorName} commented on your post`;
      if (obscure) {
        bodyText = isReply
          ? `${authorName} replied to your comment (content hidden for privacy)`
          : `${authorName} commented on your post (content hidden for privacy)`;
      } else if (c.content) {
        const snippet = c.content.length > 60 ? c.content.substring(0, 57) + '...' : c.content;
        bodyText = isReply
          ? `${authorName} replied: "${snippet}"`
          : `${authorName} commented: "${snippet}"`;
      }

      showToast(`💬 ${bodyText}`, 'info', 6000);
    });

    posts.forEach(p => {
      const authorName = p.author_display_name || p.author_username;
      let bodyText = `${authorName} published a new post`;
      if (obscure) {
        bodyText = `${authorName} published a new post (content hidden for privacy)`;
      } else if (p.content) {
        const snippet = p.content.length > 60 ? p.content.substring(0, 57) + '...' : p.content;
        bodyText = `${authorName}: "${snippet}"`;
      }

      showToast(`📌 ${bodyText}`, 'info', 6000);
    });
  }
}

function setupGlobalFetchAuthHandler() {
  const originalFetch = window.fetch;
  window.fetch = async function(...args) {
    const response = await originalFetch.apply(this, args);
    if (response.status === 401) {
      if (window.location.pathname !== '/login' && window.location.pathname !== '/register') {
        window.location.href = '/login';
      }
    }
    return response;
  };
}

function updateUnreadMessagesBadge() {
  const badge = document.getElementById('global-unread-badge');
  if (!badge) return;
  fetch('/api/messages/unread-count')
    .then(r => r.json())
    .then(data => {
      if (data.unread_count && data.unread_count > 0) {
        badge.innerText = data.unread_count;
        badge.style.display = 'inline-block';
      } else {
        badge.style.display = 'none';
      }
    })
    .catch(() => {});
}

function dismissNotice(noticeId) {
  const el = document.getElementById(noticeId);
  if (el) {
    el.style.display = 'none';
    sessionStorage.setItem('notice_dismissed_' + noticeId, 'true');
  }
}

function checkNoticeDismissal() {
  if (window.location.pathname === '/login' || window.location.pathname === '/register') {
    sessionStorage.clear();
    localStorage.removeItem('notice_dismissed_main-feed-notice');
    localStorage.removeItem('notice_dismissed_main-index-notice');
    return;
  }

  const notices = document.querySelectorAll('.dismissable-notice');
  notices.forEach(n => {
    if (sessionStorage.getItem('notice_dismissed_' + n.id) === 'true') {
      n.style.display = 'none';
    }
  });

  // Attach logout link handler to clear notice dismissal state
  const logoutLinks = document.querySelectorAll('a[href*="/logout"]');
  logoutLinks.forEach(link => {
    link.addEventListener('click', () => {
      sessionStorage.clear();
      localStorage.removeItem('notice_dismissed_main-feed-notice');
      localStorage.removeItem('notice_dismissed_main-index-notice');
    });
  });
}





function updateThemeButtonUI(theme) {
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) {
    btn.innerHTML = theme === 'dark' ? '☀️' : '🌙';
    btn.setAttribute('title', theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode');
  }
}


function previewMediaAttachment(input) {
  const previewBox = document.getElementById('media-preview-box');
  const previewImg = document.getElementById('preview-image');
  const previewVideo = document.getElementById('preview-video');

  if (!previewBox) return;

  if (input.files && input.files[0]) {
    const file = input.files[0];
    if (!file.type.startsWith('image/')) {
      if (typeof showCustomAlert === 'function') {
        showCustomAlert("The selected file format is not supported. Only image attachments are accepted.");
      } else {
        alert("The selected file format is not supported. Only image attachments are accepted.");
      }
      clearMediaAttachment();
      return;
    }
    const fileUrl = URL.createObjectURL(file);
    previewBox.style.display = 'block';

    previewImg.src = fileUrl;
    previewImg.style.display = 'block';
    if (previewVideo) previewVideo.style.display = 'none';
  } else {
    previewBox.style.display = 'none';
  }
}

// Clear Media Attachment Selection
function clearMediaAttachment() {
  const input = document.getElementById('file-input');
  const previewBox = document.getElementById('media-preview-box');
  const dropzonePreview = document.getElementById('dropzone-preview-container');
  if (input) input.value = '';
  if (previewBox) previewBox.style.display = 'none';
  if (dropzonePreview) dropzonePreview.innerHTML = '';
}

// Custom Modal Overlay Dialog Utilities
function closeCustomModal() {
  const modal = document.getElementById('custom-modal-overlay');
  if (modal) modal.style.display = 'none';
  if (window.customModalOnClose) {
    const callback = window.customModalOnClose;
    window.customModalOnClose = null;
    callback();
  }
}

function showCustomAlert(message, title = "Notice", onCloseCallback = null) {
  const modal = document.getElementById('custom-modal-overlay');
  const titleEl = document.getElementById('modal-title');
  const bodyEl = document.getElementById('modal-body');
  const footerEl = document.getElementById('modal-footer');

  if (!modal) {
    alert(message);
    if (onCloseCallback) onCloseCallback();
    return;
  }

  window.customModalOnClose = onCloseCallback;

  titleEl.innerText = title;
  bodyEl.innerHTML = `<p>${escapeHtml(message)}</p>`;
  footerEl.innerHTML = `<button id="modal-alert-ok-btn" onclick="closeCustomModal()" class="btn btn-primary btn-sm">OK</button>`;
  modal.style.display = 'flex';

  setTimeout(() => {
    const okBtn = document.getElementById('modal-alert-ok-btn');
    if (okBtn) okBtn.focus();
  }, 50);
}


function showCustomConfirm(message, title = "Confirm Action", onConfirm, confirmBtnText = "Confirm", confirmBtnClass = "btn-primary") {
  const modal = document.getElementById('custom-modal-overlay');
  const titleEl = document.getElementById('modal-title');
  const bodyEl = document.getElementById('modal-body');
  const footerEl = document.getElementById('modal-footer');

  if (!modal) {
    if (confirm(message)) onConfirm();
    return;
  }

  titleEl.innerText = title;
  bodyEl.innerHTML = `<p style="white-space: pre-line;">${escapeHtml(message)}</p>`;

  footerEl.innerHTML = `
    <button onclick="closeCustomModal()" class="btn btn-secondary btn-sm">Cancel</button>
    <button id="modal-confirm-btn" class="btn ${confirmBtnClass} btn-sm">${escapeHtml(confirmBtnText)}</button>
  `;

  document.getElementById('modal-confirm-btn').onclick = () => {
    closeCustomModal();
    if (typeof onConfirm === 'function') onConfirm();
  };

  modal.style.display = 'flex';

  setTimeout(() => {
    const confirmBtn = document.getElementById('modal-confirm-btn');
    if (confirmBtn) confirmBtn.focus();
  }, 50);
}

function showCustomPrompt(message, placeholder = "", title = "Input Required", onPromptSubmit, inputType = "text") {
  const modal = document.getElementById('custom-modal-overlay');
  const titleEl = document.getElementById('modal-title');
  const bodyEl = document.getElementById('modal-body');
  const footerEl = document.getElementById('modal-footer');

  if (!modal) {
    const val = prompt(message);
    if (val !== null && typeof onPromptSubmit === 'function') onPromptSubmit(val);
    return;
  }

  titleEl.innerText = title;
  bodyEl.innerHTML = `
    <p style="margin-bottom: 0.85rem; white-space: pre-line;">${escapeHtml(message)}</p>
    <input type="${escapeHtml(inputType)}" id="modal-prompt-input" class="form-control" placeholder="${escapeHtml(placeholder)}" onkeypress="if(event.key==='Enter') document.getElementById('modal-submit-btn').click()">
  `;

  footerEl.innerHTML = `
    <button onclick="closeCustomModal()" class="btn btn-secondary btn-sm">Cancel</button>
    <button id="modal-submit-btn" class="btn btn-primary btn-sm">Submit</button>
  `;

  setTimeout(() => {
    const inp = document.getElementById('modal-prompt-input');
    if (inp) inp.focus();
  }, 50);

  document.getElementById('modal-submit-btn').onclick = () => {
    const val = document.getElementById('modal-prompt-input').value;
    closeCustomModal();
    if (typeof onPromptSubmit === 'function') onPromptSubmit(val);
  };

  modal.style.display = 'flex';
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Image Lightbox Overlay Utilities
function updateImageOverlaySizing() {
  const modalImg = document.getElementById('image-modal-img');
  if (!modalImg || !modalImg.naturalWidth || !modalImg.naturalHeight) return;

  const w = modalImg.naturalWidth;
  const h = modalImg.naturalHeight;

  if (h > w) {
    // If height is bigger than width, height is 95% of the page
    modalImg.style.height = '95vh';
    modalImg.style.width = 'auto';
    modalImg.style.maxHeight = '95vh';
    modalImg.style.maxWidth = '95vw';
  } else {
    // Otherwise width is 95% of the page
    modalImg.style.width = '95vw';
    modalImg.style.height = 'auto';
    modalImg.style.maxWidth = '95vw';
    modalImg.style.maxHeight = '95vh';
  }
}

function openImageOverlay(src) {
  const overlay = document.getElementById('image-modal-overlay');
  const modalImg = document.getElementById('image-modal-img');
  if (!overlay || !modalImg) return;

  modalImg.onload = updateImageOverlaySizing;
  modalImg.src = src;

  if (modalImg.complete) {
    updateImageOverlaySizing();
  }

  overlay.style.display = 'flex';
}

function closeImageModal() {
  const overlay = document.getElementById('image-modal-overlay');
  if (overlay) overlay.style.display = 'none';
}

// Global listener for image clicks
document.addEventListener('click', (e) => {
  const overlay = document.getElementById('image-modal-overlay');
  if (overlay && overlay.style.display === 'flex') {
    closeImageModal();
    return;
  }

  if (e.target.tagName === 'IMG') {
    if (e.target.closest('#media-preview-box') ||
        e.target.closest('#group-preview-box') ||
        e.target.id === 'image-modal-img' ||
        e.target.closest('#image-modal-overlay') ||
        !e.target.src) {
      return;
    }
    openImageOverlay(e.target.src);
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeImageModal();
    const customModal = document.getElementById('custom-modal-overlay');
    if (customModal && customModal.style.display === 'flex') {
      closeCustomModal();
    }
  }
});

window.addEventListener('resize', () => {
  const overlay = document.getElementById('image-modal-overlay');
  if (overlay && overlay.style.display === 'flex') {
    updateImageOverlaySizing();
  }
});


// Global Share Post Helper with Web Share API and Clipboard Fallback
async function sharePost(postId) {
  const postUrl = `${window.location.origin}/post/${postId}`;

  if (navigator.share) {
    try {
      await navigator.share({
        title: 'Antisocial Post',
        url: postUrl
      });
      return;
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.warn('Navigator share error, falling back to clipboard copy:', err);
      } else {
        return; // User dismissed native share sheet
      }
    }
  }

  // Fallback to clipboard copy
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(postUrl);
      showToast('🔗 Post link copied to clipboard!', 'success');
    } else {
      const input = document.createElement('input');
      input.value = postUrl;
      document.body.appendChild(input);
      input.select();
      document.execCommand('copy');
      document.body.removeChild(input);
      showToast('🔗 Post link copied to clipboard!', 'success');
    }
  } catch (err) {
    prompt('Copy link to post:', postUrl);
  }
}

// Global Toast Notification Helper
function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = 'position: fixed; bottom: 24px; right: 24px; z-index: 99999; display: flex; flex-direction: column; gap: 10px; pointer-events: none;';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  const bgColor = type === 'success' ? '#10b981' : (type === 'danger' ? '#ef4444' : '#dc2626');
  toast.style.cssText = `background: ${bgColor}; color: #ffffff; padding: 12px 22px; border-radius: 8px; font-weight: 600; font-size: 0.9rem; box-shadow: 0 10px 25px rgba(0,0,0,0.4); pointer-events: auto; opacity: 0; transform: translateY(12px); transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);`;
  toast.innerText = message;

  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateY(0)';
  });

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(12px)';
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 250);
  }, 3000);
}

// Global Date & Time Formatting Helper respecting User Timezone Preference
function formatDateTime(isoStr, customTz = null) {
  if (!isoStr) return '';
  const dateStr = String(isoStr);
  const date = new Date(dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z');
  if (isNaN(date.getTime())) return isoStr;

  let targetTz = customTz || localStorage.getItem('user_timezone') || 'auto';

  try {
    const options = {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    };
    if (targetTz && targetTz !== 'auto') {
      options.timeZone = targetTz;
    }
    return new Intl.DateTimeFormat(undefined, options).format(date);
  } catch (err) {
    return date.toLocaleString();
  }
}

function formatTimeAgo(isoStr) {
  if (!isoStr) return '';
  const dateStr = String(isoStr);
  const date = new Date(dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z');
  if (isNaN(date.getTime())) return isoStr;

  const now = new Date();
  const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffSec < 10) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;

  return formatDateTime(isoStr);
}

async function loadUserTimezoneCache() {
  if (localStorage.getItem('user_timezone')) return;
  try {
    const res = await fetch('/api/users/profile/me');
    if (res.ok) {
      const data = await res.json();
      if (data && data.profile && data.profile.timezone) {
        localStorage.setItem('user_timezone', data.profile.timezone);
      }
    }
  } catch (err) {}
}


// Glassmorphic Toast Notification Helper
function showToast(message, category = 'info', duration = 4000) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast-item toast-${category}`;

  const iconMap = {
    success: '✅',
    danger: '⚠️',
    info: 'ℹ️'
  };

  toast.innerHTML = `
    <div style="display: flex; align-items: center; gap: 0.5rem;">
      <span style="font-size: 1.1rem;">${iconMap[category] || '📢'}</span>
      <span style="font-size: 0.88rem; font-weight: 500; color: var(--text-main);">${message}</span>
    </div>
    <button onclick="this.parentElement.remove()" style="background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1.2rem; line-height: 1; margin-left: 0.5rem;" aria-label="Close notification">&times;</button>
    <div class="toast-progress" style="transition-duration: ${duration}ms;"></div>
  `;

  container.appendChild(toast);

  const progressBar = toast.querySelector('.toast-progress');
  setTimeout(() => {
    if (progressBar) progressBar.style.width = '0%';
  }, 20);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Drag-and-Drop Media Dropzone Helper
function setupMediaDropzone(dropzoneId, inputId, previewContainerId) {
  const dropzone = document.getElementById(dropzoneId);
  const fileInput = document.getElementById(inputId);
  const previewContainer = document.getElementById(previewContainerId);
  if (!dropzone || !fileInput || !previewContainer) return;

  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, preventDefaults, false);
  });

  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => dropzone.classList.add('dragover'), false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => dropzone.classList.remove('dragover'), false);
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files.length > 0) {
      fileInput.files = files;
      handleFiles(files);
    }
  });

  dropzone.addEventListener('click', (e) => {
    if (e.target.tagName !== 'BUTTON' && !e.target.classList.contains('remove-preview-btn')) {
      fileInput.click();
    }
  });

  fileInput.addEventListener('change', () => {
    handleFiles(fileInput.files);
  });

  function handleFiles(files) {
    previewContainer.innerHTML = '';
    if (!files || files.length === 0) return;

    const file = files[0];
    if (file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'dropzone-preview-wrapper';
        wrapper.innerHTML = `
          <img src="${e.target.result}" class="preview-thumbnail" alt="Attachment preview" />
          <button type="button" class="remove-preview-btn" title="Remove attachment">&times;</button>
        `;
        wrapper.querySelector('.remove-preview-btn').addEventListener('click', (ev) => {
          ev.stopPropagation();
          fileInput.value = '';
          previewContainer.innerHTML = '';
        });
        previewContainer.appendChild(wrapper);
      };
      reader.readAsDataURL(file);
    }
  }
}

// Live Countdown Badge Helper for Ephemeral Content
function renderEphemeralBadge(expiresAtIso, isLightText = false) {
  if (!expiresAtIso) return '';
  const now = new Date();
  const expireDate = new Date(expiresAtIso.endsWith('Z') || expiresAtIso.includes('+') ? expiresAtIso : expiresAtIso + 'Z');
  const diffMs = expireDate - now;

  const extraClass = isLightText ? 'ephemeral-badge-light' : '';

  if (diffMs <= 0) return `<span class="ephemeral-badge ephemeral-urgent ${extraClass}">⏳ Expired</span>`;

  const diffMins = Math.floor(diffMs / 60000);
  const isUrgent = diffMins < 60;

  if (diffMins < 60) {
    return `<span class="ephemeral-badge ${isUrgent ? 'ephemeral-urgent' : ''} ${extraClass}">⏳ Self-destructs in ${diffMins}m</span>`;
  } else if (diffMins < 1440) {
    const hours = Math.floor(diffMins / 60);
    return `<span class="ephemeral-badge ${extraClass}">⏳ Self-destructs in ${hours}h</span>`;
  } else {
    const days = Math.floor(diffMins / 1440);
    return `<span class="ephemeral-badge ${extraClass}">⏳ Self-destructs in ${days}d</span>`;
  }
}

// Cookie & Privacy Consent Management
function checkCookieConsent() {
  const consent = localStorage.getItem('antisocial_cookie_consent');
  const banner = document.getElementById('cookie-banner');
  if (!banner) return;

  if (!consent) {
    banner.style.display = 'block';
  } else {
    banner.style.display = 'none';
  }
}

function acceptAllCookies() {
  localStorage.setItem('antisocial_cookie_consent', 'accepted_all');
  const banner = document.getElementById('cookie-banner');
  if (banner) banner.style.display = 'none';
  showToast("Your cookie preferences (All Cookies Accepted) have been saved.", "success");
}

function rejectNonEssentialCookies() {
  localStorage.setItem('antisocial_cookie_consent', 'essential_only');
  const banner = document.getElementById('cookie-banner');
  if (banner) banner.style.display = 'none';
  showToast("Opted out of non-essential cookies. Only essential cookies will be used.", "info");
}

// -------------------------------------------------------------
// WYSIWYG Rich Text Editor & Content Formatting
// -------------------------------------------------------------

function formatPostContent(rawContent) {
  if (!rawContent) return '';
  let clean = sanitizePostHtml(rawContent);
  clean = autolinkPlainUrls(clean);
  clean = embedYouTubeVideos(clean);
  clean = embedTwitterTweets(clean);
  return clean;
}

function extractYouTubeVideoIds(htmlContent) {
  if (!htmlContent) return [];
  const videoIds = [];
  const ytRegex = /(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?(?:[^"\s>]*&)?v=|embed\/|shorts\/|v\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/gi;
  let match;
  while ((match = ytRegex.exec(htmlContent)) !== null) {
    const id = match[1];
    if (id && !videoIds.includes(id)) {
      videoIds.push(id);
    }
  }
  return videoIds;
}

function embedYouTubeVideos(htmlContent) {
  if (!htmlContent) return '';
  const videoIds = extractYouTubeVideoIds(htmlContent);
  if (videoIds.length === 0) return htmlContent;

  let embedsHtml = '<div class="post-youtube-embeds">';
  videoIds.forEach(id => {
    embedsHtml += `<div class="youtube-embed-container"><iframe src="https://www.youtube.com/embed/${id}" title="YouTube video player" frameborder="0" allow="picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></div>`;
  });
  embedsHtml += '</div>';

  return htmlContent + embedsHtml;
}

function extractTwitterTweetIds(htmlContent) {
  if (!htmlContent) return [];
  const tweets = [];
  const tweetIds = new Set();
  const twRegex = /(?:https?:\/\/)?(?:www\.|mobile\.)?(?:twitter\.com|x\.com)\/([a-zA-Z0-9_]{1,15})\/status\/(\d+)/gi;
  let match;
  while ((match = twRegex.exec(htmlContent)) !== null) {
    const username = match[1];
    const tweetId = match[2];
    if (tweetId && !tweetIds.has(tweetId)) {
      tweetIds.add(tweetId);
      tweets.push({ username, tweetId });
    }
  }
  return tweets;
}

function embedTwitterTweets(htmlContent) {
  if (!htmlContent) return '';
  const tweets = extractTwitterTweetIds(htmlContent);
  if (tweets.length === 0) return htmlContent;

  const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';

  let embedsHtml = '<div class="post-twitter-embeds">';
  tweets.forEach(t => {
    embedsHtml += `<div class="twitter-embed-container"><blockquote class="twitter-tweet" data-theme="${currentTheme}" data-dnt="true"><a href="https://twitter.com/${t.username}/status/${t.tweetId}"></a></blockquote></div>`;
  });
  embedsHtml += '</div>';

  triggerTwitterWidgetsLoad();

  return htmlContent + embedsHtml;
}

function triggerTwitterWidgetsLoad() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  if (!document.getElementById('twitter-wjs')) {
    const script = document.createElement('script');
    script.id = 'twitter-wjs';
    script.src = 'https://platform.twitter.com/widgets.js';
    script.async = true;
    script.charset = 'utf-8';
    script.onload = () => {
      if (window.twttr && window.twttr.widgets) {
        window.twttr.widgets.load();
      }
    };
    document.head.appendChild(script);
  } else if (window.twttr && window.twttr.widgets) {
    setTimeout(() => {
      try {
        window.twttr.widgets.load();
      } catch (e) {}
    }, 50);
  }
}

function sanitizePostHtml(html) {
  if (!html) return '';
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const allowedTags = new Set(['B', 'STRONG', 'I', 'EM', 'U', 'S', 'STRIKE', 'DEL', 'A', 'BR', 'P', 'DIV', 'SPAN', 'BLOCKQUOTE']);

    function cleanNode(node) {
      const children = Array.from(node.childNodes);
      children.forEach(child => {
        if (child.nodeType === Node.ELEMENT_NODE) {
          if (!allowedTags.has(child.tagName)) {
            const textNode = doc.createTextNode(child.textContent);
            child.parentNode.replaceChild(textNode, child);
          } else {
            const attrs = Array.from(child.attributes);
            attrs.forEach(attr => {
              if (child.tagName === 'A') {
                if (!['href', 'target', 'rel', 'title'].includes(attr.name.toLowerCase())) {
                  child.removeAttribute(attr.name);
                }
              } else {
                child.removeAttribute(attr.name);
              }
            });

            if (child.tagName === 'A') {
              let href = child.getAttribute('href') || '';
              if (href.toLowerCase().trim().startsWith('javascript:') || href.toLowerCase().trim().startsWith('data:')) {
                href = '#';
              } else if (href && !href.match(/^(https?:\/\/|\/|mailto:)/i)) {
                if (href.match(/^www\./i)) {
                  href = 'http://' + href;
                } else {
                  href = 'https://' + href;
                }
              }
              child.setAttribute('href', href);
              child.setAttribute('target', '_blank');
              child.setAttribute('rel', 'noopener noreferrer');
            }

            cleanNode(child);
          }
        }
      });
    }

    cleanNode(doc.body);

    if (doc.body.children.length === 1) {
      const first = doc.body.children[0];
      if ((first.tagName === 'DIV' || first.tagName === 'P') && first.attributes.length === 0) {
        return first.innerHTML;
      }
    }

    return doc.body.innerHTML;
  } catch (e) {
    return escapeHtmlText(html);
  }
}

function autolinkPlainUrls(text) {
  if (!text) return '';
  const urlRegex = /(?:https?:\/\/|www\.)[^\s<]+[^\s<.,:;"')\]>]/gi;

  return text.replace(urlRegex, (url) => {
    let href = url;
    if (url.toLowerCase().startsWith('www.')) {
      href = 'http://' + url;
    }
    return `<a href="${escapeHtmlAttr(href)}" target="_blank" rel="noopener noreferrer">${escapeHtmlText(url)}</a>`;
  });
}

function escapeHtmlAttr(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escapeHtmlText(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

const WYSIWYG_EMOJIS = [
  // Smileys & Emotions
  { char: "😀", name: "Grinning Face", keywords: "smile happy joy grin" },
  { char: "😃", name: "Grinning Face with Big Eyes", keywords: "smile happy joy" },
  { char: "😄", name: "Grinning Face with Smiling Eyes", keywords: "smile happy joy" },
  { char: "😁", name: "Beaming Face with Smiling Eyes", keywords: "smile happy grin" },
  { char: "😆", name: "Grinning Squinting Face", keywords: "laugh haha smile" },
  { char: "😅", name: "Grinning Face with Sweat", keywords: "sweat phew smile" },
  { char: "😂", name: "Face with Tears of Joy", keywords: "laugh cry lol tears" },
  { char: "🤣", name: "Rolling on the Floor Laughing", keywords: "rofl lol laugh" },
  { char: "😊", name: "Smiling Face with Smiling Eyes", keywords: "smile happy blush" },
  { char: "😇", name: "Smiling Face with Halo", keywords: "angel halo innocent" },
  { char: "🥰", name: "Smiling Face with Hearts", keywords: "love heart adore" },
  { char: "😍", name: "Smiling Face with Heart-Eyes", keywords: "love heart eyes" },
  { char: "🤩", name: "Star-Struck", keywords: "star excited amazed" },
  { char: "😘", name: "Face Blowing a Kiss", keywords: "kiss love heart" },
  { char: "😋", name: "Face Savoring Food", keywords: "yum tasty food" },
  { char: "😛", name: "Face with Tongue", keywords: "tongue silly playful" },
  { char: "😜", name: "Winking Face with Tongue", keywords: "wink tongue silly" },
  { char: "🤪", name: "Zany Face", keywords: "crazy goofy silly" },
  { char: "🤑", name: "Money-Mouth Face", keywords: "money dollar rich" },
  { char: "🤗", name: "Hugging Face", keywords: "hug warm friends" },
  { char: "🤭", name: "Face with Hand Over Mouth", keywords: "oops giggle secret" },
  { char: "🤫", name: "Shushing Face", keywords: "quiet hush secret" },
  { char: "🤔", name: "Thinking Face", keywords: "think hmm ponder" },
  { char: "🤐", name: "Zipper-Mouth Face", keywords: "secret quiet zip" },
  { char: "🤨", name: "Face with Raised Eyebrow", keywords: "skeptical distrust" },
  { char: "😐", name: "Neutral Face", keywords: "meh neutral blank" },
  { char: "😑", name: "Expressionless Face", keywords: "meh expressionless" },
  { char: "😶", name: "Face Without Mouth", keywords: "silent quiet" },
  { char: "😏", name: "Smirking Face", keywords: "smirk sly" },
  { char: "😒", name: "Unamused Face", keywords: "meh bored annoyed" },
  { char: "🙄", name: "Face with Rolling Eyes", keywords: "eye roll whatever" },
  { char: "😬", name: "Grimacing Face", keywords: "grimace awkward nervous" },
  { char: "🤥", name: "Lying Face", keywords: "pinocchio lie liar" },
  { char: "😌", name: "Relieved Face", keywords: "relieved phew calm" },
  { char: "😔", name: "Pensive Face", keywords: "sad thoughtful" },
  { char: "😪", name: "Sleepy Face", keywords: "sleep tired" },
  { char: "🤤", name: "Drooling Face", keywords: "drool delicious" },
  { char: "😴", name: "Sleeping Face", keywords: "zzz sleep tired" },
  { char: "😷", name: "Face with Medical Mask", keywords: "sick mask doctor" },
  { char: "🤒", name: "Face with Thermometer", keywords: "sick fever ill" },
  { char: "🤕", name: "Face with Head-Bandage", keywords: "hurt injured bandage" },
  { char: "🤢", name: "Nauseated Face", keywords: "gross sick vomit" },
  { char: "🤮", name: "Face Vomiting", keywords: "sick puke vomit" },
  { char: "🤧", name: "Sneezing Face", keywords: "sneeze sick tissue" },
  { char: "🥵", name: "Hot Face", keywords: "hot sweat heat" },
  { char: "🥶", name: "Cold Face", keywords: "freezing cold ice" },
  { char: "🥴", name: "Woozy Face", keywords: "dizzy drunk woozy" },
  { char: "😵", name: "Dizzy Face", keywords: "dizzy knocked out" },
  { char: "🤯", name: "Exploding Head", keywords: "mind blown shocked" },
  { char: "🤠", name: "Cowboy Hat Face", keywords: "cowboy hat" },
  { char: "🥳", name: "Partying Face", keywords: "party celebrate hat" },
  { char: "😎", name: "Smiling Face with Sunglasses", keywords: "cool sunglasses rad" },
  { char: "🤓", name: "Nerd Face", keywords: "nerd glasses geek" },
  { char: "🧐", name: "Face with Monocle", keywords: "monocle curious inspect" },

  // Gestures & People
  { char: "👍", name: "Thumbs Up", keywords: "yes approve like good" },
  { char: "👎", name: "Thumbs Down", keywords: "no dislike bad" },
  { char: "👏", name: "Clapping Hands", keywords: "applause clap bravo" },
  { char: "🙌", name: "Raising Hands", keywords: "celebrate hooray praise" },
  { char: "👐", name: "Open Hands", keywords: "open hug" },
  { char: "🤲", name: "Palms Up Together", keywords: "pray open" },
  { char: "🤝", name: "Handshake", keywords: "agree deal friendship" },
  { char: "🙏", name: "Folded Hands", keywords: "pray please thank you" },
  { char: "✌️", name: "Victory Hand", keywords: "peace victory v" },
  { char: "🤟", name: "Love-You Gesture", keywords: "love rock" },
  { char: "🤘", name: "Sign of the Horns", keywords: "rock metal" },
  { char: "👊", name: "Oncoming Fist", keywords: "fist bump punch" },
  { char: "✊", name: "Raised Fist", keywords: "power fist" },
  { char: "🤛", name: "Left-Facing Fist", keywords: "fist bump" },
  { char: "🤜", name: "Right-Facing Fist", keywords: "fist bump" },
  { char: "🖐️", name: "Hand with Fingers Splayed", keywords: "hand five stop" },
  { char: "✋", name: "Raised Hand", keywords: "stop high five" },
  { char: "👋", name: "Waving Hand", keywords: "wave hello goodbye" },
  { char: "💪", name: "Flexed Biceps", keywords: "strong muscle power" },
  { char: "💅", name: "Nail Polish", keywords: "beauty sassy" },
  { char: "✍️", name: "Writing Hand", keywords: "write sign pen" },

  // Hearts & Symbols
  { char: "❤️", name: "Red Heart", keywords: "love heart red" },
  { char: "🧡", name: "Orange Heart", keywords: "love heart orange" },
  { char: "💛", name: "Yellow Heart", keywords: "love heart yellow" },
  { char: "💚", name: "Green Heart", keywords: "love heart green" },
  { char: "💙", name: "Blue Heart", keywords: "love heart blue" },
  { char: "💜", name: "Purple Heart", keywords: "love heart purple" },
  { char: "🖤", name: "Black Heart", keywords: "love heart black" },
  { char: "🤍", name: "White Heart", keywords: "love heart white" },
  { char: "🤎", name: "Brown Heart", keywords: "love heart brown" },
  { char: "💔", name: "Broken Heart", keywords: "sad heartbreak" },
  { char: "❣️", name: "Heart Exclamation", keywords: "love heart heavy" },
  { char: "💕", name: "Two Hearts", keywords: "love hearts" },
  { char: "💞", name: "Revolving Hearts", keywords: "love hearts" },
  { char: "💓", name: "Beating Heart", keywords: "love heart pulse" },
  { char: "💗", name: "Growing Heart", keywords: "love heart" },
  { char: "💖", name: "Sparkling Heart", keywords: "love heart sparkle" },
  { char: "💘", name: "Heart with Arrow", keywords: "cupid love heart" },
  { char: "💝", name: "Heart with Ribbon", keywords: "gift love heart" },
  { char: "✨", name: "Sparkles", keywords: "clean shiny magic" },
  { char: "🌟", name: "Glowing Star", keywords: "star shiny yellow" },
  { char: "💫", name: "Dizzy Symbol", keywords: "star shooting" },
  { char: "⚡", name: "High Voltage", keywords: "lightning bolt power" },
  { char: "💥", name: "Collision", keywords: "boom explosion bang" },
  { char: "🔥", name: "Fire", keywords: "hot flame lit fire" },
  { char: "🎉", name: "Party Popper", keywords: "celebrate party tada" },
  { char: "🎊", name: "Confetti Ball", keywords: "party celebrate" },
  { char: "🎈", name: "Balloon", keywords: "party birthday" },
  { char: "🏆", name: "Trophy", keywords: "winner gold cup" },
  { char: "🥇", name: "1st Place Medal", keywords: "first gold medal winner" },

  // Nature, Objects & Food
  { char: "🐱", name: "Cat Face", keywords: "cat pet kitten" },
  { char: "🐶", name: "Dog Face", keywords: "dog pet puppy" },
  { char: "🦊", name: "Fox", keywords: "fox animal" },
  { char: "🦁", name: "Lion", keywords: "lion king animal" },
  { char: "🐯", name: "Tiger Face", keywords: "tiger animal" },
  { char: "🐻", name: "Bear", keywords: "bear animal" },
  { char: "🐼", name: "Panda", keywords: "panda bear animal" },
  { char: "🦄", name: "Unicorn", keywords: "unicorn magic" },
  { char: "🚀", name: "Rocket", keywords: "space launch rocket" },
  { char: "🌈", name: "Rainbow", keywords: "rainbow color sky" },
  { char: "☀️", name: "Sun", keywords: "sun sunny weather" },
  { char: "🌙", name: "Crescent Moon", keywords: "moon night" },
  { char: "🍕", name: "Pizza", keywords: "pizza food slice" },
  { char: "🍔", name: "Hamburger", keywords: "burger food fast food" },
  { char: "🍟", name: "French Fries", keywords: "fries food fast food" },
  { char: "🌮", name: "Taco", keywords: "taco food mexican" },
  { char: "☕", name: "Hot Beverage", keywords: "coffee tea hot" },
  { char: "🍺", name: "Beer Mug", keywords: "beer drink alcohol" },
  { char: "🥂", name: "Clinking Glasses", keywords: "cheers drink toast" },
  { char: "⚽", name: "Soccer Ball", keywords: "soccer football sports" },
  { char: "🎮", name: "Video Game Controller", keywords: "gaming game play" },
  { char: "🎲", name: "Game Die", keywords: "dice game luck" },
  { char: "🎸", name: "Guitar", keywords: "music rock guitar" },
  { char: "🎧", name: "Headphones", keywords: "music listen audio" }
];

function setupWysiwygEditor(wrapperId, placeholderText = "What's on your mind?", isCompact = false) {
  const wrapper = document.getElementById(wrapperId);
  if (!wrapper) return null;

  wrapper.innerHTML = `<div class="wysiwyg-container ${isCompact ? 'wysiwyg-compact' : ''}" style="white-space: normal;"><div class="wysiwyg-toolbar" style="white-space: normal;"><button type="button" class="wysiwyg-btn" data-cmd="bold" title="Bold (Ctrl+B)"><b>B</b></button><button type="button" class="wysiwyg-btn" data-cmd="italic" title="Italic (Ctrl+I)"><i>I</i></button><button type="button" class="wysiwyg-btn" data-cmd="underline" title="Underline (Ctrl+U)"><u>U</u></button><button type="button" class="wysiwyg-btn" data-cmd="strikeThrough" title="Strikethrough"><s>S</s></button><span class="wysiwyg-divider"></span><button type="button" class="wysiwyg-btn wysiwyg-link-btn" title="Insert Link (Ctrl+K)">🔗 Link</button><div class="wysiwyg-emoji-menu-wrapper"><button type="button" class="wysiwyg-btn wysiwyg-emoji-btn" title="Insert Emoji">😀</button><div class="wysiwyg-emoji-menu"><div class="emoji-menu-header"><input type="text" class="emoji-search-input" placeholder="🔍 Search emojis..."></div><div class="emoji-menu-grid"></div><div class="emoji-hover-footer">Hover over an emoji</div></div></div></div><div class="wysiwyg-editor" contenteditable="true" data-placeholder="${escapeHtmlAttr(placeholderText)}"></div><div class="char-counter wysiwyg-char-counter" style="text-align: right; margin-top: 0.25rem; font-size: 0.78rem;">0 / 10,000</div><input type="hidden" class="wysiwyg-hidden-input" name="content"></div>`;

  const toolbar = wrapper.querySelector('.wysiwyg-toolbar');
  const editor = wrapper.querySelector('.wysiwyg-editor');
  const hiddenInput = wrapper.querySelector('.wysiwyg-hidden-input');
  const wysiwygCounter = wrapper.querySelector('.wysiwyg-char-counter');

  function syncContent() {
    let html = editor.innerHTML || '';
    let rawText = editor.innerText || editor.textContent || '';
    if (rawText.trim() === '') {
      html = '';
    } else {
      html = sanitizePostHtml(html);
    }
    hiddenInput.value = html;

    const len = rawText.length;
    if (wysiwygCounter) {
      wysiwygCounter.textContent = `${len.toLocaleString()} / 10,000`;
      wysiwygCounter.classList.remove('warning', 'exceeded');
      if (len > 10000) wysiwygCounter.classList.add('exceeded');
      else if (len >= 9000) wysiwygCounter.classList.add('warning');
    }
  }

  editor.addEventListener('input', syncContent);
  editor.addEventListener('blur', syncContent);
  editor.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      syncContent();
      const form = wrapper.closest('form');
      if (form) {
        if (typeof form.requestSubmit === 'function') {
          form.requestSubmit();
        } else {
          form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
        }
      }
    }
  });

  toolbar.querySelectorAll('.wysiwyg-btn[data-cmd]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const cmd = btn.getAttribute('data-cmd');
      document.execCommand(cmd, false, null);
      editor.focus();
      syncContent();
      updateActiveStates();
    });
  });

  const linkBtn = toolbar.querySelector('.wysiwyg-link-btn');
  if (linkBtn) {
    linkBtn.addEventListener('click', (e) => {
      e.preventDefault();
      openWysiwygLinkModal(editor, syncContent);
    });
  }

  // Emoji Menu Handler
  const emojiBtn = toolbar.querySelector('.wysiwyg-emoji-btn');
  const emojiMenu = toolbar.querySelector('.wysiwyg-emoji-menu');
  const emojiGrid = toolbar.querySelector('.emoji-menu-grid');
  const emojiSearch = toolbar.querySelector('.emoji-search-input');
  const emojiFooter = toolbar.querySelector('.emoji-hover-footer');
  let savedEmojiRange = null;

  function renderEmojiGrid(filterText = '') {
    const query = filterText.trim().toLowerCase();
    const filtered = WYSIWYG_EMOJIS.filter(e => {
      if (!query) return true;
      return e.name.toLowerCase().includes(query) ||
             e.keywords.toLowerCase().includes(query) ||
             e.char.includes(query);
    });

    if (filtered.length === 0) {
      emojiGrid.innerHTML = `<div style="grid-column: span 8; color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 0.75rem 0;">No matching emojis</div>`;
      return;
    }

    emojiGrid.innerHTML = filtered.map(e => `
      <button type="button" class="emoji-item-btn" title="${escapeHtmlAttr(e.name)}" data-emoji="${e.char}" data-name="${escapeHtmlAttr(e.name)}">${e.char}</button>
    `).join('');

    emojiGrid.querySelectorAll('.emoji-item-btn').forEach(btn => {
      btn.addEventListener('mouseenter', () => {
        if (emojiFooter) {
          const name = btn.getAttribute('data-name');
          const char = btn.getAttribute('data-emoji');
          emojiFooter.innerText = `${char} ${name}`;
        }
      });

      btn.addEventListener('mouseleave', () => {
        if (emojiFooter) {
          emojiFooter.innerText = 'Hover over an emoji';
        }
      });

      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        const emoji = btn.getAttribute('data-emoji');
        insertEmojiIntoEditor(editor, emoji, savedEmojiRange, syncContent);
        emojiMenu.style.display = 'none';
      });
    });
  }

  if (emojiBtn && emojiMenu) {
    renderEmojiGrid();

    emojiBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const sel = window.getSelection();
      if (sel.rangeCount > 0) {
        savedEmojiRange = sel.getRangeAt(0).cloneRange();
      }

      const isVisible = emojiMenu.style.display === 'block';
      emojiMenu.style.display = isVisible ? 'none' : 'block';
      if (!isVisible && emojiSearch) {
        emojiSearch.value = '';
        renderEmojiGrid();
        setTimeout(() => emojiSearch.focus(), 50);
      }
    });

    if (emojiSearch) {
      emojiSearch.addEventListener('input', (e) => {
        renderEmojiGrid(e.target.value);
      });
    }

    document.addEventListener('click', (e) => {
      if (!wrapper.contains(e.target)) {
        emojiMenu.style.display = 'none';
      }
    });
  }


  editor.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      openWysiwygLinkModal(editor, syncContent);
    }
  });

  function updateActiveStates() {
    ['bold', 'italic', 'underline', 'strikeThrough'].forEach(cmd => {
      const b = toolbar.querySelector(`[data-cmd="${cmd}"]`);
      if (b) {
        if (document.queryCommandState(cmd)) {
          b.classList.add('active');
        } else {
          b.classList.remove('active');
        }
      }
    });
  }

  editor.addEventListener('keyup', updateActiveStates);
  editor.addEventListener('mouseup', updateActiveStates);

  return {
    editor,
    hiddenInput,
    getContent: () => {
      syncContent();
      return hiddenInput.value;
    },
    setContent: (html) => {
      editor.innerHTML = html || '';
      syncContent();
    },
    clear: () => {
      editor.innerHTML = '';
      syncContent();
    }
  };
}

function insertEmojiIntoEditor(editor, emoji, savedRange, syncCallback) {
  editor.focus();
  const sel = window.getSelection();
  if (savedRange) {
    sel.removeAllRanges();
    sel.addRange(savedRange);
  }
  document.execCommand('insertText', false, emoji);
  if (syncCallback) syncCallback();
}


function openWysiwygLinkModal(editor, syncCallback) {
  let modal = document.getElementById('wysiwyg-link-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'wysiwyg-link-modal';
    modal.className = 'wysiwyg-modal-overlay';
    modal.innerHTML = `
      <div class="wysiwyg-modal-card">
        <h4 style="margin-bottom: 0.85rem; color: var(--primary-red); font-size: 1.1rem; display: flex; align-items: center; gap: 0.4rem;">
          🔗 Insert Link
        </h4>
        <div class="form-group" style="margin-bottom: 0.75rem;">
          <label style="font-size: 0.85rem; font-weight: 600;">Link Text (Display Label)</label>
          <input type="text" id="wysiwyg-link-text" class="form-control" placeholder="e.g. My Portfolio or Click Here">
        </div>
        <div class="form-group" style="margin-bottom: 1.25rem;">
          <label style="font-size: 0.85rem; font-weight: 600;">Link URL</label>
          <input type="text" id="wysiwyg-link-url" class="form-control" placeholder="https://example.com">
        </div>
        <div style="display: flex; gap: 0.5rem; justify-content: flex-end;">
          <button type="button" id="wysiwyg-modal-cancel" class="btn btn-secondary btn-sm">Cancel</button>
          <button type="button" id="wysiwyg-modal-insert" class="btn btn-primary btn-sm">Insert Link</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  }

  const selection = window.getSelection();
  let selectedText = '';
  let savedRange = null;

  if (selection.rangeCount > 0) {
    savedRange = selection.getRangeAt(0).cloneRange();
    selectedText = selection.toString().trim();
  }

  const textInput = document.getElementById('wysiwyg-link-text');
  const urlInput = document.getElementById('wysiwyg-link-url');
  const cancelBtn = document.getElementById('wysiwyg-modal-cancel');
  const insertBtn = document.getElementById('wysiwyg-modal-insert');

  textInput.value = selectedText;
  urlInput.value = '';
  modal.style.display = 'flex';

  setTimeout(() => {
    if (selectedText) {
      urlInput.focus();
    } else {
      textInput.focus();
    }
  }, 50);

  function closeModal() {
    modal.style.display = 'none';
  }

  cancelBtn.onclick = closeModal;

  function handleInsert() {
    let url = urlInput.value.trim();
    let text = textInput.value.trim();

    if (!url) {
      alert("Please enter a URL for the link.");
      urlInput.focus();
      return;
    }

    if (!text) {
      text = url;
    }

    if (!url.match(/^(https?:\/\/|\/|mailto:)/i)) {
      if (url.match(/^www\./i)) {
        url = 'http://' + url;
      } else {
        url = 'https://' + url;
      }
    }

    closeModal();
    editor.focus();

    if (savedRange) {
      selection.removeAllRanges();
      selection.addRange(savedRange);
    }

    const linkHtml = `<a href="${escapeHtmlAttr(url)}" target="_blank" rel="noopener noreferrer">${escapeHtmlText(text)}</a>`;
    document.execCommand('insertHTML', false, linkHtml);

    if (syncCallback) syncCallback();
  }

  insertBtn.onclick = handleInsert;

  const keyHandler = (e) => {
    if (modal.style.display === 'flex') {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleInsert();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        closeModal();
      }
    }
  };

  urlInput.onkeydown = keyHandler;
  textInput.onkeydown = keyHandler;
}

// -------------------------------------------------------------
// Central Post Editing with WYSIWYG Editor
// -------------------------------------------------------------

const activePostEditWysiwygMap = {};

function enablePostEdit(postId) {
  const contentEl = document.getElementById(`post-content-text-${postId}`);
  if (!contentEl) return;

  const rawText = contentEl.getAttribute('data-raw-content') || contentEl.innerText || '';

  contentEl.innerHTML = `<div id="post-edit-box-${postId}" style="margin: 0.25rem 0; white-space: normal;"><div id="post-edit-wysiwyg-wrapper-${postId}"></div><div style="display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 0.4rem;"><button type="button" onclick="cancelPostEdit(${postId})" class="btn btn-secondary btn-sm" style="padding: 0.25rem 0.75rem; font-size: 0.82rem;">Cancel</button><button type="button" onclick="submitPostEdit(${postId})" class="btn btn-primary btn-sm" style="padding: 0.25rem 0.75rem; font-size: 0.82rem;">Save Edit</button></div></div>`;

  const wysiwyg = setupWysiwygEditor(`post-edit-wysiwyg-wrapper-${postId}`, "Edit your post...", true);
  if (wysiwyg) {
    wysiwyg.setContent(rawText);
    activePostEditWysiwygMap[postId] = wysiwyg;
    if (wysiwyg.editor) {
      wysiwyg.editor.focus();
    }
  }
}

async function submitPostEdit(postId) {
  const wysiwyg = activePostEditWysiwygMap[postId];
  let newContent = '';
  if (wysiwyg) {
    newContent = wysiwyg.getContent().trim();
  } else {
    const input = document.getElementById(`post-edit-input-${postId}`);
    newContent = input ? input.value.trim() : '';
  }

  const token = document.body.getAttribute('data-token') || (typeof window.token !== 'undefined' ? window.token : null);

  try {
    const res = await fetch(`/api/posts/${postId}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ content: newContent })
    });

    if (res.ok) {
      const data = await res.json();
      delete activePostEditWysiwygMap[postId];
      const contentEl = document.getElementById(`post-content-text-${postId}`);
      if (contentEl) {
        contentEl.setAttribute('data-raw-content', data.content);
        contentEl.innerHTML = formatPostContent(data.content || '');
      }
    } else {
      const err = await res.json();
      showCustomAlert(err.detail || "Failed to update post content", "Edit Error");
    }
  } catch (err) {
    showCustomAlert("Error updating post: " + err.message, "Network Error");
  }
}

function cancelPostEdit(postId) {
  delete activePostEditWysiwygMap[postId];
  const contentEl = document.getElementById(`post-content-text-${postId}`);
  if (contentEl) {
    const rawText = contentEl.getAttribute('data-raw-content') || '';
    contentEl.innerHTML = formatPostContent(rawText);
  }
}

// -------------------------------------------------------------
// Comment Section Emoji Picker Functions
// -------------------------------------------------------------

function toggleCommentEmojiPicker(postId, btnEl) {
  let menu = document.getElementById(`comment-emoji-menu-${postId}`);
  if (!menu) return;

  const isVisible = menu.style.display === 'block';

  document.querySelectorAll('.comment-emoji-menu').forEach(m => {
    if (m !== menu) m.style.display = 'none';
  });

  if (isVisible) {
    menu.style.display = 'none';
  } else {
    menu.style.display = 'block';
    renderCommentEmojiGrid(postId);
    const searchInput = menu.querySelector('.emoji-search-input');
    if (searchInput) {
      searchInput.value = '';
      setTimeout(() => searchInput.focus(), 50);
    }
  }
}

function renderCommentEmojiGrid(postId, filterText = '') {
  const grid = document.getElementById(`comment-emoji-grid-${postId}`);
  const footer = document.getElementById(`comment-emoji-footer-${postId}`);
  if (!grid) return;

  const query = filterText.trim().toLowerCase();
  const filtered = WYSIWYG_EMOJIS.filter(e => {
    if (!query) return true;
    return e.name.toLowerCase().includes(query) ||
           e.keywords.toLowerCase().includes(query) ||
           e.char.includes(query);
  });

  if (filtered.length === 0) {
    grid.innerHTML = `<div style="grid-column: span 8; color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 0.75rem 0;">No matching emojis</div>`;
    return;
  }

  grid.innerHTML = filtered.map(e => `
    <button type="button" class="emoji-item-btn" title="${escapeHtmlAttr(e.name)}" data-emoji="${e.char}" data-name="${escapeHtmlAttr(e.name)}">${e.char}</button>
  `).join('');

  grid.querySelectorAll('.emoji-item-btn').forEach(btn => {
    btn.addEventListener('mouseenter', () => {
      if (footer) {
        const name = btn.getAttribute('data-name');
        const char = btn.getAttribute('data-emoji');
        footer.innerText = `${char} ${name}`;
      }
    });

    btn.addEventListener('mouseleave', () => {
      if (footer) {
        footer.innerText = 'Hover over an emoji';
      }
    });

    btn.addEventListener('click', (ev) => {
      ev.preventDefault();
      const emoji = btn.getAttribute('data-emoji');
      const input = document.getElementById(`comment-input-${postId}`);
      if (input) {
        const start = input.selectionStart || input.value.length;
        const end = input.selectionEnd || input.value.length;
        const text = input.value;
        input.value = text.substring(0, start) + emoji + text.substring(end);
        input.focus();
        input.setSelectionRange(start + emoji.length, start + emoji.length);
      }
      const menu = document.getElementById(`comment-emoji-menu-${postId}`);
      if (menu) menu.style.display = 'none';
    });
  });
}

function filterCommentEmojis(postId, filterText) {
  renderCommentEmojiGrid(postId, filterText);
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.comment-emoji-wrapper')) {
    document.querySelectorAll('.comment-emoji-menu').forEach(m => {
      m.style.display = 'none';
    });
  }
});

// Comment Tree & Replies Helpers
function formatMentions(text) {
  if (!text) return '';
  return text.replace(/@([a-zA-Z0-9_]+):?/g, (match, username) => {
    const hasColon = match.endsWith(':');
    return `<a href="/profile/${username}" class="comment-mention-tag">@${username}${hasColon ? ':' : ''}</a>`;
  });
}

function renderCommentTreeHtml(comments, postId, currentUserId, currentUserRole, postAuthorId) {
  if (!comments || comments.length === 0) {
    return `<div style="color: var(--text-muted); font-size: 0.85rem; padding: 0.25rem 0;" id="no-comments-msg-${postId}">No comments yet. Be the first to comment!</div>`;
  }

  const commentMap = {};
  comments.forEach(c => { commentMap[c.id] = c; });

  const topLevel = [];
  const repliesMap = {};

  comments.forEach(c => {
    if (c.parent_id) {
      // Find root parent ID for single-level indentation
      let curr = c;
      while (curr.parent_id && commentMap[curr.parent_id]) {
        curr = commentMap[curr.parent_id];
      }
      const rootId = curr.id !== c.id ? curr.id : c.parent_id;
      if (!repliesMap[rootId]) repliesMap[rootId] = [];
      repliesMap[rootId].push(c);
    } else {
      topLevel.push(c);
    }
  });

  topLevel.sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));

  function renderSingleComment(c, isChild = false) {
    const cName = c.author_display_name || c.author_username;
    const cInitial = c.author_username ? c.author_username.charAt(0).toUpperCase() : 'U';
    const cAvatarHtml = c.author_avatar 
      ? `<img src="${c.author_avatar}" style="width:26px; height:26px; border-radius:50%; object-fit:cover;" />`
      : `<div class="user-avatar" style="width:26px; height:26px; font-size:0.75rem; display:flex; align-items:center; justify-content:center; flex-shrink:0;">${cInitial}</div>`;

    const isModOrAdmin = currentUserRole === 'admin' || currentUserRole === 'moderator';
    const canDelete = currentUserId && (currentUserId === c.author_id || currentUserId === postAuthorId || isModOrAdmin);
    const deleteBtn = canDelete 
      ? `<button onclick="deleteComment(${postId}, ${c.id})" class="comment-delete-btn" title="Delete Comment"><span class="delete-icon">🗑️</span></button>`
      : '';

    const replyBtn = currentUserId 
      ? `<button onclick="setCommentReplyTarget(${postId}, ${c.id}, '${escapeHtml(c.author_username)}')" class="comment-reply-btn">Reply</button>`
      : '';

    const dateStr = c.created_at ? formatDateTime(c.created_at) : '';
    const contentHtml = formatMentions(formatPostContent(c.content || ''));

    return `
      <div class="comment-item" id="comment-${c.id}">
        <a href="/profile/${c.author_username}" class="comment-avatar-link">
          ${cAvatarHtml}
        </a>
        <div class="comment-body">
          <div class="comment-text-content">
            <a href="/profile/${c.author_username}" class="comment-author">${escapeHtml(cName)}</a>
            <span class="comment-text">${contentHtml}</span>
          </div>
          <div class="comment-actions-meta">
            <span class="comment-date">${dateStr}</span>
            ${replyBtn}
            ${deleteBtn}
          </div>
        </div>
      </div>
    `;
  }

  let html = '';
  topLevel.forEach(parentCmt => {
    const childReplies = repliesMap[parentCmt.id] || [];
    childReplies.sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));

    html += `<div class="comment-group" id="comment-group-${parentCmt.id}">`;
    html += renderSingleComment(parentCmt, false);

    if (childReplies.length > 0) {
      const replyCount = childReplies.length;
      html += `
        <button type="button" class="toggle-replies-btn" id="toggle-replies-btn-${parentCmt.id}" onclick="toggleCommentReplies(${parentCmt.id})">
          💬 ${replyCount} ${replyCount === 1 ? 'Reply' : 'Replies'} ▲
        </button>
        <div class="comment-replies-container" id="replies-container-${parentCmt.id}" style="display: block;">
      `;
      childReplies.forEach(childCmt => {
        html += renderSingleComment(childCmt, true);
      });
      html += `</div>`;
    }

    html += `</div>`;
  });

  return html;
}

function toggleCommentReplies(parentId) {
  const container = document.getElementById(`replies-container-${parentId}`);
  const btn = document.getElementById(`toggle-replies-btn-${parentId}`);
  if (!container || !btn) return;

  const isHidden = container.style.display === 'none';
  if (isHidden) {
    container.style.display = 'block';
    const count = container.querySelectorAll('.comment-item').length;
    btn.innerHTML = `💬 ${count} ${count === 1 ? 'Reply' : 'Replies'} ▲`;
  } else {
    container.style.display = 'none';
    const count = container.querySelectorAll('.comment-item').length;
    btn.innerHTML = `💬 ${count} ${count === 1 ? 'Reply' : 'Replies'} ▼`;
  }
}

function setCommentReplyTarget(postId, commentId, username) {
  const input = document.getElementById(`comment-input-${postId}`);
  if (!input) return;

  input.dataset.parentId = commentId;
  const targetTag = document.getElementById(`comment-reply-target-${postId}`);
  if (targetTag) {
    targetTag.innerHTML = `Replying to <strong>@${escapeHtml(username)}</strong> <button type="button" onclick="clearCommentReplyTarget(${postId})" style="background:none; border:none; color:var(--primary-red); cursor:pointer; font-weight:bold; padding:0 0.2rem;">✕</button>`;
    targetTag.style.display = 'inline-flex';
  }

  const prefix = `@${username}: `;
  if (!input.value.startsWith(prefix)) {
    input.value = prefix + input.value;
  }
  updateCommentCharCounter(input, postId);
  input.focus();
}

function clearCommentReplyTarget(postId) {
  const input = document.getElementById(`comment-input-${postId}`);
  if (input) {
    delete input.dataset.parentId;
  }
  const targetTag = document.getElementById(`comment-reply-target-${postId}`);
  if (targetTag) {
    targetTag.style.display = 'none';
    targetTag.innerHTML = '';
  }
}

function updateInputCharCounter(inputEl, counterId, maxLen) {
  if (!inputEl) return;
  const counterEl = document.getElementById(counterId);
  if (!counterEl) return;
  const len = inputEl.value ? inputEl.value.length : 0;
  counterEl.textContent = `${len.toLocaleString()} / ${maxLen.toLocaleString()}`;
  counterEl.classList.remove('warning', 'exceeded');
  if (len >= maxLen) {
    counterEl.classList.add('exceeded');
  } else if (len >= maxLen * 0.9) {
    counterEl.classList.add('warning');
  }
}

function updateCommentCharCounter(inputEl, postId) {
  updateInputCharCounter(inputEl, `comment-counter-${postId}`, 280);
}



