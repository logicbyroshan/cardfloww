import React, { useState, useEffect } from 'react';
import { Search, X, User, School, CreditCard, Building, Table2 } from 'lucide-react';
import { clientApi } from '../../services/api';

export default function GlobalSearchModal({ isOpen, onClose }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    const q = query.toLowerCase().trim();
    setLoading(true);

    const timer = setTimeout(async () => {
      let combined = [];

      // 1. Search Organisations / Clients
      try {
        const data = await clientApi.getActive({ search: query, page_size: 10 });
        const list = Array.isArray(data?.clients) ? data.clients : Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : [];
        list.forEach(c => {
          combined.push({
            type: 'Organisation',
            title: c.name || 'Organisation',
            subtitle: `${c.email || ''} • ${c.phone || ''} (${c.status || 'active'})`,
          });
        });
      } catch {}

      // 2. Search Local Storage Organisations
      try {
        const local = JSON.parse(localStorage.getItem('cf_custom_clients') || '[]');
        local.filter(c => c.name?.toLowerCase().includes(q) || c.email?.toLowerCase().includes(q)).forEach(c => {
          if (!combined.some(x => x.title === c.name)) {
            combined.push({
              type: 'Organisation',
              title: c.name,
              subtitle: `${c.email || ''} • ${c.phone || ''} (active)`,
            });
          }
        });
      } catch {}

      // 3. Search Local Storage Tables
      try {
        const localTbls = JSON.parse(localStorage.getItem('cf_custom_tables') || '[]');
        localTbls.filter(t => t.name?.toLowerCase().includes(q) || t.client_name?.toLowerCase().includes(q)).forEach(t => {
          combined.push({
            type: 'Table',
            title: t.name,
            subtitle: `${t.client_name || 'Organisation'} • ${t.fields?.length || 0} fields`,
          });
        });
      } catch {}

      setResults(combined.slice(0, 15));
      setLoading(false);
    }, 250);

    return () => clearTimeout(timer);
  }, [query]);

  if (!isOpen) return null;

  return (
    <div className="center-modal-overlay" style={{ alignItems: 'flex-start', paddingTop: '10vh' }}>
      <div
        className="center-modal-panel"
        style={{ width: '580px', height: 'auto', maxHeight: '80vh', padding: '1.25rem', backdropFilter: 'blur(16px)', background: '#ffffff', borderRadius: '12px', boxShadow: '0 20px 40px rgba(0,0,0,0.2)' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '0.75rem', marginBottom: '1rem' }}>
          <Search size={20} color="#64748b" />
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type to search organisations, tables, cards, or emails..."
            style={{ flex: 1, background: 'transparent', border: 'none', color: '#0f172a', fontSize: '1rem', outline: 'none', fontFamily: 'inherit' }}
          />
          {query && (
            <button onClick={() => setQuery('')} style={{ background: 'transparent', border: 'none', color: '#9ca3af', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
              <X size={16} />
            </button>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '350px', overflowY: 'auto' }}>
          {loading ? (
            <div style={{ padding: '20px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>Searching...</div>
          ) : results.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
              {query ? `No results found for "${query}"` : 'Start typing to search across the entire system'}
            </div>
          ) : (
            results.map((res, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.85rem',
                  padding: '0.75rem 1rem',
                  borderRadius: '8px',
                  background: '#f8fafc',
                  border: '1px solid #f1f5f9',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={e => e.currentTarget.style.background = '#eff6ff'}
                onMouseLeave={e => e.currentTarget.style.background = '#f8fafc'}
              >
                <div style={{ width: '32px', height: '32px', borderRadius: '6px', background: res.type === 'Organisation' ? '#dbeafe' : '#fef3c7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {res.type === 'Organisation' ? <Building size={16} color="#2563eb" /> : <Table2 size={16} color="#d97706" />}
                </div>
                <div>
                  <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#1e293b' }}>{res.title}</div>
                  <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{res.subtitle}</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
