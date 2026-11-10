import React from 'react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('Aurelia App ErrorBoundary caught an error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          backgroundColor: '#08090B',
          color: '#F5F3EE',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2rem',
          fontFamily: 'Inter, -apple-system, sans-serif'
        }}>
          <div style={{
            maxWidth: '600px',
            width: '100%',
            backgroundColor: '#121418',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '16px',
            padding: '2.5rem',
            boxShadow: '0 20px 50px rgba(0, 0, 0, 0.7)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
              <div style={{
                width: '12px',
                height: '12px',
                borderRadius: '50%',
                backgroundColor: '#F07878',
                boxShadow: '0 0 10px #F07878'
              }} />
              <span style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '0.75rem',
                color: '#E6C17A',
                letterSpacing: '0.15em',
                textTransform: 'uppercase'
              }}>
                AURELIA RECOVERY SYSTEM
              </span>
            </div>

            <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 0.75rem 0', color: '#FFFFFF' }}>
              An interface error occurred
            </h1>

            <p style={{ fontSize: '0.875rem', color: '#A1A4AA', margin: '0 0 1.5rem 0', lineHeight: 1.6 }}>
              The application encountered an unexpected runtime exception. Details are provided below:
            </p>

            <div style={{
              backgroundColor: '#08090B',
              border: '1px solid rgba(255, 255, 255, 0.05)',
              borderRadius: '8px',
              padding: '1rem',
              marginBottom: '1.5rem',
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.75rem',
              color: '#F07878',
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
              maxHeight: '160px'
            }}>
              {this.state.error?.toString() || 'Unknown error'}
            </div>

            <div style={{ display: 'flex', gap: '1rem' }}>
              <button
                onClick={() => window.location.reload()}
                style={{
                  background: 'linear-gradient(180deg, #D4A965 0%, #B88B46 100%)',
                  color: '#08090B',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                  padding: '0.65rem 1.4rem',
                  borderRadius: '8px',
                  border: 'none',
                  cursor: 'pointer'
                }}
              >
                Reload Application
              </button>
              <button
                onClick={this.handleReset}
                style={{
                  background: '#181B20',
                  color: '#F5F3EE',
                  fontWeight: 500,
                  fontSize: '0.875rem',
                  padding: '0.65rem 1.4rem',
                  borderRadius: '8px',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  cursor: 'pointer'
                }}
              >
                Return to Landing
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
