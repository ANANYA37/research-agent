import { useErrorBoundary } from 'react-error-boundary';

export default function ErrorFallback({ error }) {
  const { resetBoundary } = useErrorBoundary();

  return (
    <div className="error-banner" style={{ margin: '2rem', display: 'flex', flexDirection: 'column', gap: '1rem', alignItems: 'flex-start' }}>
      <h3>Something went wrong</h3>
      <p style={{ color: 'var(--text-secondary)' }}>{error.message}</p>
      <button onClick={resetBoundary} className="primary-action">
        Try Again
      </button>
    </div>
  );
}
