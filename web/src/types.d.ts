// Type definitions for window.openai API
declare global {
  interface Window {
    openai: {
      // Tool data
      toolInput: any;
      toolOutput: any;
      toolResponseMetadata: any;
      widgetState: any;

      // Layout & theme
      theme: 'light' | 'dark';
      displayMode: 'inline' | 'pip' | 'fullscreen';
      maxHeight: number;
      locale: string;
      userAgent: {
        device: { type: 'mobile' | 'tablet' | 'desktop' | 'unknown' };
        capabilities: { hover: boolean; touch: boolean };
      };
      safeArea: {
        insets: { top: number; bottom: number; left: number; right: number };
      };

      // API methods
      callTool: (name: string, args: Record<string, unknown>) => Promise<any>;
      sendFollowUpMessage: (args: { prompt: string }) => Promise<void>;
      openExternal: (payload: { href: string }) => void;
      requestDisplayMode: (args: { mode: 'inline' | 'pip' | 'fullscreen' }) => Promise<{ mode: string }>;
      setWidgetState: (state: any) => Promise<void>;
    };
  }
}

export {};

