import { useCallback, useRef, useState } from "react";
import { readShowDraft, writeShowDraft } from "../lib/showDraft";

export function useShowDraft(key, initial, { memoryOnly = false } = {}) {
  const initialRef = useRef(initial);
  const [value, setValue] = useState(() => readShowDraft(key, initialRef.current, memoryOnly));
  const update = useCallback((next) => {
    // Read the store synchronously so rapid updates don't overwrite each other.
    const current = readShowDraft(key, initialRef.current, memoryOnly);
    const value = typeof next === "function" ? next(current) : next;
    writeShowDraft(key, value, memoryOnly);
    setValue(value);
  }, [key, memoryOnly]);
  return [value, update];
}
