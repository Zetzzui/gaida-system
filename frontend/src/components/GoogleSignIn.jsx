import { useEffect, useRef } from 'react';

const GIS_SRC = 'https://accounts.google.com/gsi/client';

export default function GoogleSignIn({ clientId, onCredential, text = 'continue_with' }) {
  const buttonRef = useRef(null);

  useEffect(() => {
    if (!clientId || !buttonRef.current) return undefined;

    const init = () => {
      if (!window.google?.accounts) {
        console.error('Google Identity Services failed to load');
        return;
      }
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => {
          if (response?.credential) onCredential(response.credential);
        },
      });
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: 'outline',
        size: 'large',
        shape: 'rectangular',
        text,
        width: '100%',
        logo_alignment: 'left',
      });
    };

    if (window.google?.accounts) {
      init();
      return undefined;
    }

    const script = document.createElement('script');
    script.src = GIS_SRC;
    script.async = true;
    script.defer = true;
    script.onload = init;
    document.head.appendChild(script);

    return () => {
      if (window.google?.accounts) window.google.accounts.id.cancel();
    };
  }, [clientId, onCredential, text]);

  if (!clientId) {
    return (
      <div className="text-xs text-center text-gray-400 py-3">
        Google sign-in is not configured.
      </div>
    );
  }

  return <div ref={buttonRef} />;
}