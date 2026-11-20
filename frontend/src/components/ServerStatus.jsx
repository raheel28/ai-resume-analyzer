import { useEffect, useState } from "react";
import { health } from "../api.js";

/**
 * Shows a banner only if the API is slow to answer, e.g. a free Render
 * instance waking up after being idle. Silent when the server is already up.
 */
export default function ServerStatus() {
  const [state, setState] = useState("checking"); // checking | waking | ready | down
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const start = Date.now();
    const slow = setTimeout(() => !cancelled && setState((s) => (s === "checking" ? "waking" : s)), 2500);
    const tick = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000);

    health()
      .then(() => !cancelled && setState("ready"))
      .catch(() => !cancelled && setState("down"))
      .finally(() => {
        clearTimeout(slow);
        clearInterval(tick);
      });
    return () => {
      cancelled = true;
      clearTimeout(slow);
      clearInterval(tick);
    };
  }, []);

  if (state === "waking") {
    return (
      <div className="banner server" role="status" aria-live="polite">
        <span className="spinner" aria-hidden="true" />
        <span>
          Waking up the server… the free hosting sleeps when nobody's used it for a while.
          This takes about a minute the first time. <span className="muted">({seconds}s)</span>
        </span>
      </div>
    );
  }
  if (state === "down") {
    return (
      <div className="banner server error" role="alert">
        Couldn't reach the server. It may be restarting. Refresh the page in a minute.
      </div>
    );
  }
  return null;
}
