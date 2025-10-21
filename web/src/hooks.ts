import { useSyncExternalStore, useCallback } from 'react';

const SET_GLOBALS_EVENT_TYPE = 'openai:set_globals';

// Hook to subscribe to a specific window.openai global value
export function useOpenAiGlobal<K extends keyof typeof window.openai>(
  key: K
): typeof window.openai[K] {
  return useSyncExternalStore(
    (onChange) => {
      const handleSetGlobal = (event: any) => {
        const value = event.detail?.globals?.[key];
        if (value !== undefined) {
          onChange();
        }
      };

      window.addEventListener(SET_GLOBALS_EVENT_TYPE, handleSetGlobal, {
        passive: true,
      });

      return () => {
        window.removeEventListener(SET_GLOBALS_EVENT_TYPE, handleSetGlobal);
      };
    },
    () => window.openai?.[key]
  );
}

// Convenience hooks for common values
export function useToolOutput() {
  return useOpenAiGlobal('toolOutput');
}

export function useTheme() {
  return useOpenAiGlobal('theme');
}

export function useDisplayMode() {
  return useOpenAiGlobal('displayMode');
}

