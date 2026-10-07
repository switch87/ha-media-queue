// Update elements that already exist, in place: re-creating them on every
// state update would drop the keyboard focus (and restart hover states).

function setAttribute(el, name, value) {
  if (value === null || value === undefined) {
    if (el.hasAttribute(name)) el.removeAttribute(name);
  } else if (el.getAttribute(name) !== value) {
    el.setAttribute(name, value);
  }
}

/**
 * Update a button: spec {icon, title, label, pressed?, active?, disabled?}.
 * pressed undefined removes aria-pressed (no toggle); active undefined leaves
 * the "on" class alone.
 */
export function updateButton(button, spec) {
  if (button.title !== spec.title) button.title = spec.title;
  setAttribute(button, "aria-label", spec.label);
  setAttribute(button, "aria-pressed", spec.pressed === undefined ? null : String(spec.pressed));
  const disabled = Boolean(spec.disabled);
  if (button.disabled !== disabled) button.disabled = disabled;
  if (spec.active !== undefined) button.classList.toggle("on", spec.active);
  const icon = button.firstElementChild;
  if (icon && icon.icon !== spec.icon) icon.icon = spec.icon;
}

/** Set the text of an element when it differs. */
export function updateText(el, text) {
  if (el.textContent !== text) el.textContent = text;
}

/** Show a range with value (hide it for null); leave it alone while focused. */
export function updateRange(input, value, focused) {
  input.hidden = value === null;
  if (value !== null && !focused && input.value !== String(value)) input.value = String(value);
}
