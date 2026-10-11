import { useCallback, useEffect, useState } from "react";
import { api } from "../../api.js";

export const CIPHERS = ["binary", "morse", "caesar", "polybius", "vigenere", "hex", "braille", "ascii", "book"];

export const adm = (path, options = {}) => api(`/api/admin${path}`, { ...options, as: "admin" });

/** Loads an admin resource and exposes a reload; `run` wraps a mutation with error reporting. */
export function useAdmin(path, notify) {
  const [data, setData] = useState(null);
  const reload = useCallback(
    () => adm(path).then(setData).catch((err) => notify(err.message, true)),
    [path, notify]
  );
  useEffect(() => {
    reload();
  }, [reload]);
  const run = async (action, done) => {
    try {
      const result = await action();
      if (done) notify(typeof done === "function" ? done(result) : done);
      await reload();
      return result;
    } catch (err) {
      notify(err.message, true);
      return null;
    }
  };
  return [data, run, reload];
}

export function Field({ label, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="label">{label}</span>
      {children}
    </label>
  );
}
