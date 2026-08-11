import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '40px 20px',
            textAlign: 'center',
            background: '#ffffff',
            minHeight: '300px',
            width: '100%',
            height: '100%',
          }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              background: '#fef2f2',
              color: '#dc2626',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px solid #fca5a5',
              marginBottom: '16px',
              boxShadow: '0 4px 12px rgba(220,38,38,0.1)',
            }}
          >
            <AlertCircle size={28} />
          </div>
          <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
            Unable to Load View
          </h3>
          <p style={{ fontSize: '12px', color: '#64748b', maxWidth: '420px', margin: '0 0 16px 0', lineHeight: 1.5 }}>
            {this.state.error?.message || 'An unexpected error occurred while rendering this section.'}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="btn btn-primary btn-sm"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              padding: '6px 16px',
              borderRadius: '4px',
            }}
          >
            <RefreshCw size={13} /> Try Reloading View
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
