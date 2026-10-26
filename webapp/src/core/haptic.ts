let label: HTMLLabelElement | null = null;

/** iOS Safari has no vibration API, but flipping a native `switch` checkbox
 * ticks the Taptic Engine (iOS 18+, also in an installed app): a label tapped
 * from the user's own gesture does it. */
function iosTick(): void {
  if (!label) {
    const input = document.createElement("input");
    input.type = "checkbox";
    input.setAttribute("switch", "");
    input.tabIndex = -1;
    label = document.createElement("label");
    label.setAttribute("aria-hidden", "true");
    label.style.cssText =
      "position:fixed;left:-100px;top:0;width:1px;height:1px;opacity:0;pointer-events:none;";
    label.append(input);
    document.body.append(label);
  }
  label.click();
}

/** A short tap under the finger: Telegram's own haptics inside it, the
 * vibration motor on Android, the switch trick on an iPhone. */
export function tick(): void {
  try {
    // Telegram's script defines the object in a plain browser too, where it
    // does nothing: only real Init Data says the app runs inside Telegram.
    const app = window.Telegram?.WebApp;
    if (app?.initData && app.HapticFeedback) app.HapticFeedback.impactOccurred("medium");
    else if (typeof navigator.vibrate === "function") navigator.vibrate(12);
    else iosTick();
  } catch {
    // No haptics: the tap still works.
  }
}
