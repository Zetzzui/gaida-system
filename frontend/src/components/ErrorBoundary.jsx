import { Component } from 'react';

// Top-level error boundary: any uncaught render/effect error in a child
// becomes a friendly crash page with a reload button instead of a blank
// white screen. Class components are required for boundaries (React docs).
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // Log the real error so it's not silent; the UI still shows the fallback.
    console.error('[GAIDA] Uncaught error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="min-h-screen flex items-center justify-center p-6"
          style={{ background: '#F7FAF9' }}
        >
          <div className="max-w-md w-full text-center">
            <h1 className="text-xl font-bold" style={{ color: '#2E3B44' }}>
              Something went wrong
            </h1>
            <p className="mt-2 text-sm" style={{ color: '#5C6F78' }}>
              An unexpected error occurred. Your session data is safe — try
              reloading the page.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-5 px-4 py-2 rounded-lg text-sm font-semibold text-white"
              style={{ background: '#5E8FBD' }}
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}