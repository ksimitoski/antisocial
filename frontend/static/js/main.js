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
  const token = document.body.getAttribute('data-token') || (typeof token !== 'undefined' ? token : null);
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
  const token = document.body.getAttribute('data-token') || (typeof token !== 'undefined' ? token : null);
  if (!token) return;

  setTimeout(pollBrowserNotifications, 3000);
  setInterval(pollBrowserNotifications, 15000);
}

async function pollBrowserNotifications() {
  const token = document.body.getAttribute('data-token') || (typeof token !== 'undefined' ? token : null);
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
      let bodyText = `${authorName} commented on your post`;
      if (obscure) {
        bodyText = `${authorName} commented on your post (content hidden for privacy)`;
      } else if (c.content) {
        const snippet = c.content.length > 60 ? c.content.substring(0, 57) + '...' : c.content;
        bodyText = `${authorName} commented: "${snippet}"`;
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
  footerEl.innerHTML = `<button onclick="closeCustomModal()" class="btn btn-primary btn-sm">OK</button>`;
  modal.style.display = 'flex';
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
  }
});

window.addEventListener('resize', () => {
  const overlay = document.getElementById('image-modal-overlay');
  if (overlay && overlay.style.display === 'flex') {
    updateImageOverlaySizing();
  }
});


// Global Share Post Helper with Web Share API and Clipboard Fallback
async function sharePost(postId, postText = '') {
  const postUrl = `${window.location.origin}/post/${postId}`;

  if (navigator.share) {
    try {
      await navigator.share({
        title: 'Antisocial Post',
        text: postText ? (postText.length > 100 ? postText.substring(0, 97) + '...' : postText) : 'Check out this post on Antisocial!',
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
  return clean;
}

function sanitizePostHtml(html) {
  if (!html) return '';
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const allowedTags = new Set(['B', 'STRONG', 'I', 'EM', 'U', 'S', 'STRIKE', 'A', 'BR', 'P', 'DIV', 'SPAN']);

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
              if (href && !href.match(/^(https?:\/\/|\/|mailto:)/i)) {
                if (href.match(/^www\./i)) {
                  href = 'http://' + href;
                } else {
                  href = 'https://' + href;
                }
                child.setAttribute('href', href);
              }
              child.setAttribute('target', '_blank');
              child.setAttribute('rel', 'noopener noreferrer');
            }

            cleanNode(child);
          }
        }
      });
    }

    cleanNode(doc.body);
    return doc.body.innerHTML;
  } catch (e) {
    return escapeHtml(html);
  }
}

function autolinkPlainUrls(html) {
  if (!html) return '';
  const combinedRegex = /(<a\s+[^>]*>[\s\S]*?<\/a>)|((?:https?:\/\/|www\.)[^\s<]+[^\s<.,:;"')\]>])/gi;

  return html.replace(combinedRegex, (match, aTag, url) => {
    if (aTag) return aTag;

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

function setupWysiwygEditor(wrapperId, placeholderText = "What's on your mind?") {
  const wrapper = document.getElementById(wrapperId);
  if (!wrapper) return null;

  wrapper.innerHTML = `
    <div class="wysiwyg-container">
      <div class="wysiwyg-toolbar">
        <button type="button" class="wysiwyg-btn" data-cmd="bold" title="Bold (Ctrl+B)"><b>B</b></button>
        <button type="button" class="wysiwyg-btn" data-cmd="italic" title="Italic (Ctrl+I)"><i>I</i></button>
        <button type="button" class="wysiwyg-btn" data-cmd="underline" title="Underline (Ctrl+U)"><u>U</u></button>
        <button type="button" class="wysiwyg-btn" data-cmd="strikeThrough" title="Strikethrough"><s>S</s></button>
        <span class="wysiwyg-divider"></span>
        <button type="button" class="wysiwyg-btn wysiwyg-link-btn" title="Insert Link (Ctrl+K)">🔗 Link</button>
      </div>
      <div class="wysiwyg-editor" contenteditable="true" data-placeholder="${escapeHtmlAttr(placeholderText)}"></div>
      <input type="hidden" class="wysiwyg-hidden-input" name="content">
    </div>
  `;

  const toolbar = wrapper.querySelector('.wysiwyg-toolbar');
  const editor = wrapper.querySelector('.wysiwyg-editor');
  const hiddenInput = wrapper.querySelector('.wysiwyg-hidden-input');

  function syncContent() {
    let html = editor.innerHTML;
    if (html === '<br>' || html.trim() === '') {
      html = '';
    }
    hiddenInput.value = html;
  }

  editor.addEventListener('input', syncContent);
  editor.addEventListener('blur', syncContent);

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

