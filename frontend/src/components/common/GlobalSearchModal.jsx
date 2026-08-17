import React, { useEffect, useState } from 'react';
import { Command } from 'cmdk';
import { Building, Table2 } from 'lucide-react';
import { clientApi, schemaApi } from '../../services/api';

// Styles — visually identical to the original modal
const S = {
  overlay: {
    position: 'fixed',
    inset: 0,
    zIndex: 9999,
    background: 'rgba(0,0,0,0.55)',
    backdropFilter: 'blur(4px)',
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'center',
    paddingTop: '10vh',
  },
  panel: {
    width: '580px',
    maxHeight: '80vh',
    overflow: 'hidden',
    background: '#ffffff',
    borderRadius: '12px',
    boxShadow: '0 20px 40px rgba(0,0,0,0.2)',
    display: 'flex',
    flexDirection: 'column',
  },
  input: {
    width: '100%',
    padding: '1rem 1.25rem',
    border: 'none',
    borderBottom: '1px solid #e2e8f0',
    outline: 'none',
    fontSize: '1rem',
    fontFamily: 'inherit',
    color: '#0f172a',
    background: 'transparent',
    boxSizing: 'border-box',
  },
  list: {
    overflowY: 'auto',
    maxHeight: '350px',
    padding: '0.5rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  empty: {
    padding: '20px',
    textAlign: 'center',
    color: '#94a3b8',
    fontSize: '13px',
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.85rem',
    padding: '0.75rem 1rem',
    borderRadius: '8px',
    background: '#f8fafc',
    border: '1px solid #f1f5f9',
    cursor: 'pointer',
    outline: 'none',
    listStyle: 'none',
  },
  icon: (type) => ({
    width: '32px',
    height: '32px',
    borderRadius: '6px',
    flexShrink: 0,
    background: type === 'Organisation' ? '#dbeafe' : '#fef3c7',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  }),
};

export default function GlobalSearchModal({ isOpen, onClose }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  // Reset on open/close
  useEffect(() => {
    if (!isOpen) {
      setQuery('');
      setResults([]);
    }
  }, [isOpen]);

  // Escape key closes modal
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  // Debounced search
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }
    const q = query.toLowerCase().trim();
    setLoading(true);
    const timer = setTimeout(async () => {
      let combined = [];
      try {
        const [clientData, schemaData] = await Promise.allSettled([
          clientApi.getActive({ search: query, page_size: 10 }),
          schemaApi.getSchemas({ search: query }),
        ]);

        if (clientData.status === 'fulfilled' && clientData.value) {
          const list = Array.isArray(clientData.value?.clients)
            ? clientData.value.clients
            : Array.isArray(clientData.value?.results)
              ? clientData.value.results
              : Array.isArray(clientData.value)
                ? clientData.value
                : [];
          list.forEach((c) =>
            combined.push({
              type: 'Organisation',
              title: c.name || 'Organisation',
              subtitle: `${c.email || ''} • ${c.phone || ''} (${c.status || 'active'})`,
            })
          );
        }

        if (schemaData.status === 'fulfilled' && schemaData.value) {
          const tList = Array.isArray(schemaData.value?.tables)
            ? schemaData.value.tables
            : Array.isArray(schemaData.value?.results)
              ? schemaData.value.results
              : Array.isArray(schemaData.value)
                ? schemaData.value
                : [];
          tList
            .filter((t) => t.name?.toLowerCase().includes(q) || t.client_name?.toLowerCase().includes(q))
            .forEach((t) =>
              combined.push({
                type: 'Table',
                title: t.name,
                subtitle: `${t.client_name || t.organisation_name || 'Organisation'} • ${t.fields?.length || 0} fields`,
              })
            );
        }
      } catch (err) {
        console.warn('Global search error:', err);
      }
      setResults(combined.slice(0, 15));
      setLoading(false);
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  if (!isOpen) return null;

  return (
    <div
      style={S.overlay}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <Command style={S.panel} shouldFilter={false} label="Global Search — CardFlow">
        {/* Command.Input is wired via onValueChange — the correct cmdk API */}
        <Command.Input
          style={S.input}
          placeholder="Search organisations, tables, cards or emails…"
          value={query}
          onValueChange={setQuery}
          autoFocus
        />
        <Command.List style={S.list}>
          {loading && (
            <Command.Loading>
              <div style={S.empty}>Searching…</div>
            </Command.Loading>
          )}
          <Command.Empty style={S.empty}>
            {query ? `No results for "${query}"` : 'Start typing to search across the entire system'}
          </Command.Empty>
          {results.map((res, idx) => (
            <Command.Item
              key={`${res.type}-${idx}`}
              value={`${res.type}-${res.title}-${idx}`}
              style={S.item}
              onSelect={onClose}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#eff6ff';
                e.currentTarget.style.borderColor = '#bfdbfe';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = '#f8fafc';
                e.currentTarget.style.borderColor = '#f1f5f9';
              }}
            >
              <div style={S.icon(res.type)}>
                {res.type === 'Organisation' ? (
                  <Building size={16} color="#2563eb" />
                ) : (
                  <Table2 size={16} color="#d97706" />
                )}
              </div>
              <div>
                <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#1e293b' }}>{res.title}</div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{res.subtitle}</div>
              </div>
            </Command.Item>
          ))}
        </Command.List>
      </Command>
    </div>
  );
}
