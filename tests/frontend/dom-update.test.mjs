import { test } from "node:test";
import assert from "node:assert/strict";

import { updateButton, updateRange, updateText } from "../../custom_components/media_queue/frontend/lib/dom-update.js";

/** A small stand-in for a DOM element that records writes. */
class Fake {
  constructor(child = null) {
    this.attrs = new Map();
    this.classes = new Set();
    this.title = "";
    this.disabled = false;
    this.hidden = false;
    this.value = "";
    this.textContent = "";
    this.firstElementChild = child;
    this.writes = 0;
    this.classList = { toggle: (name, on) => (on ? this.classes.add(name) : this.classes.delete(name)) };
  }
  hasAttribute(name) {
    return this.attrs.has(name);
  }
  getAttribute(name) {
    return this.attrs.get(name) ?? null;
  }
  setAttribute(name, value) {
    this.writes += 1;
    this.attrs.set(name, value);
  }
  removeAttribute(name) {
    this.writes += 1;
    this.attrs.delete(name);
  }
}

test("a button is updated in place: icon, title, name, pressed, disabled, class", () => {
  const icon = { icon: "mdi:play" };
  const button = new Fake(icon);
  updateButton(button, { icon: "mdi:shuffle-variant", title: "Shuffle: on", label: "Shuffle", pressed: true, active: true });
  assert.equal(icon.icon, "mdi:shuffle-variant");
  assert.equal(button.title, "Shuffle: on");
  assert.equal(button.getAttribute("aria-label"), "Shuffle");
  assert.equal(button.getAttribute("aria-pressed"), "true");
  assert.equal(button.disabled, false);
  assert.ok(button.classes.has("on"));

  const writes = button.writes;
  updateButton(button, { icon: "mdi:shuffle-variant", title: "Shuffle: on", label: "Shuffle", pressed: true, active: true });
  assert.equal(button.writes, writes, "nothing written when nothing changed");

  updateButton(button, { icon: "mdi:repeat", title: "Repeat: off", label: "Repeat: off", disabled: true });
  assert.equal(button.hasAttribute("aria-pressed"), false);
  assert.equal(button.disabled, true);
  assert.ok(button.classes.has("on"), "active left alone when not given");
  updateButton(button, { icon: "mdi:repeat", title: "x", label: "x", active: false });
  assert.equal(button.classes.has("on"), false);
  updateButton(new Fake(), { icon: "mdi:x", title: "no icon child", label: "y" });
});

test("text only changes when it differs", () => {
  const el = new Fake();
  updateText(el, "a");
  assert.equal(el.textContent, "a");
  el.textContent = "a";
  updateText(el, "a");
  assert.equal(el.textContent, "a");
});

test("a range keeps the value the user is dragging", () => {
  const input = new Fake();
  updateRange(input, 40, false);
  assert.equal(input.value, "40");
  assert.equal(input.hidden, false);
  updateRange(input, 50, true);
  assert.equal(input.value, "40");
  updateRange(input, null, false);
  assert.equal(input.hidden, true);
  assert.equal(input.value, "40");
});
