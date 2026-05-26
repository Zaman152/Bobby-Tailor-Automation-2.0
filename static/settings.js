/**
 * Bobby Tailor — Settings Page
 * Handles loading, displaying, and saving application settings.
 */

const MASKED_PLACEHOLDER = "••••••••";

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    populateForm(data);
  } catch (err) {
    showMsg("Failed to load settings: " + err.message, "error");
  }
}

function populateForm(data) {
  for (const [key, value] of Object.entries(data)) {
    // Skip meta fields like STACKCT_PASSWORD_set
    if (key.endsWith("_set")) continue;

    const el = document.getElementById(key);
    if (!el) continue;

    const isSensitive = el.dataset.sensitive === "true";
    const isSet = data[`${key}_set`] === true;

    if (el.type === "checkbox") {
      el.checked = String(value).toLowerCase() === "true";
    } else if (el.tagName === "SELECT") {
      el.value = value || "";
    } else if (isSensitive) {
      // Show masked placeholder if value is set
      if (isSet) {
        el.value = "";
        el.placeholder = MASKED_PLACEHOLDER;
        el.dataset.hasValue = "true";
      } else {
        el.dataset.hasValue = "false";
      }
      updateSensitiveBadge(key, isSet);
      attachSensitiveHandlers(el);
    } else {
      el.value = value || "";
    }
  }
}

function updateSensitiveBadge(key, isSet) {
  const badge = document.getElementById(`${key}_badge`);
  if (!badge) return;
  if (isSet) {
    badge.textContent = "Set";
    badge.className = "field-set-badge";
  } else {
    badge.textContent = "Not set";
    badge.className = "field-unset-badge";
  }
}

function attachSensitiveHandlers(input) {
  input.addEventListener("focus", () => {
    // Clear masked placeholder on focus so user can type new value
    if (input.placeholder === MASKED_PLACEHOLDER && !input.value) {
      input.placeholder = "Enter new value to change";
    }
  });

  input.addEventListener("blur", () => {
    // Restore masked placeholder if user didn't type anything
    if (!input.value && input.dataset.hasValue === "true") {
      input.placeholder = MASKED_PLACEHOLDER;
    }
  });
}

function collectFormData() {
  const data = {};
  const form = document.querySelector(".settings-form");
  if (!form) return data;

  form.querySelectorAll("input, select").forEach((el) => {
    const key = el.name || el.id;
    if (!key) return;
    if (key.startsWith("_")) return; // skip meta attributes

    const isSensitive = el.dataset.sensitive === "true";

    if (el.type === "checkbox") {
      data[key] = el.checked ? "true" : "false";
    } else if (isSensitive) {
      // Send actual value if user typed something, empty string if unchanged
      data[key] = el.value.trim();
    } else {
      data[key] = el.value.trim();
    }
  });

  return data;
}

async function saveSettings(event) {
  if (event) event.preventDefault();

  const btn = document.getElementById("saveBtn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Saving…';

  const data = collectFormData();
  clearMsg();

  try {
    const res = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const result = await res.json();

    if (!res.ok || result.error) {
      showMsg(result.error || "Save failed", "error");
      return;
    }

    showMsg(result.message || "Settings saved.", "success");

    if (result.restart_required) {
      showWarning("⚠ Restart the server for credential changes to take effect.");
    }

    // Reload to show updated state
    if (result.settings) {
      populateForm(result.settings);
    } else {
      await loadSettings();
    }
  } catch (err) {
    showMsg("Save failed: " + err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Save Settings";
  }
}

function showMsg(text, type) {
  const el = document.getElementById("msgArea");
  if (!el) return;
  el.innerHTML = `<div class="msg-${type}">${escHtml(text)}</div>`;
  setTimeout(() => clearMsg(), 8000);
}

function showWarning(text) {
  const el = document.getElementById("msgArea");
  if (!el) return;
  el.innerHTML += `<div class="msg-warning">${escHtml(text)}</div>`;
}

function clearMsg() {
  const el = document.getElementById("msgArea");
  if (el) el.innerHTML = "";
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

document.addEventListener("DOMContentLoaded", loadSettings);
