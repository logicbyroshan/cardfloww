import React, { useEffect, useState } from 'react';
import { Command } from 'cmdk';
import { Building, Table2, CreditCard } from 'lucide-react';
import { clientApi, schemaApi, cardApi } from '../../services/api';

// Styles — visually matching app aesthetics
const S = {
  overlay: {
    position: 'fixed',
    inset: 0,
    zIndex: 9999,
    background: 'rgba(0,0,0,0.65)',
    backdropFilter: 'blur(4px)',
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'center',
    paddingTop: '10vh',
  },
  panel: {
    width: '620px',
    maxHeight: '80vh',
    overflow: 'hidden',
    background: '#1e293b',
    color: '#ffffff',
    borderRadius: '12px',
    border: '1px solid #334155',
    boxShadow: '0 20px 40px rgba(0,0,0,0.5)',
    display: 'flex',
    flexDirection: 'column',
  },
  input: {
    width: '100%',
    padding: '1rem 1.25rem',
    border: 'none',
    borderBottom: '1px solid #334155',
    outline: 'none',
    fontSize: '1rem',
    fontFamily: 'inherit',
    color: '#ffffff',
    background: '#0f172a',
    boxSizing: 'border-box',
  },
  list: {
    overflowY: 'auto',
    maxHeight: '380px',
    padding: '0.5rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  empty: {
    padding: '24px',
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
    background: '#0f172a',
    border: '1px solid #334155',
    cursor: 'pointer',
    outline: 'none',
    listStyle: 'none',
    transition: 'background 0.15s, border-color 0.15s',
  },
  icon: (type) => ({
    width: '32px',
    height: '32px',
    borderRadius: '6px',
    flexShrink: 0,
    background: type === 'Organisation' ? '#1e3a8a' : type === 'Table' ? '#7c2d12' : '#064e3b',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  }),
};

export default function GlobalSearchModal({ isOpen, onClose, onNavigate }) {
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
        const [clientData, schemaData, cardData] = await Promise.allSettled([
          clientApi.getActive({ search: query, page_size: 8 }),
          schemaApi.getSchemas({ search: query }),
          cardApi.globalSearch ? cardApi.globalSearch(query) : Promise.resolve(null),
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
              id: c.id,
              raw: c,
              title: c.name || c.school_name || 'Organisation',
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
            .filter((t) => (t.name || '').toLowerCase().includes(q) || (t.client_name || '').toLowerCase().includes(q))
            .forEach((t) =>
              combined.push({
                type: 'Table',
                id: t.id,
                title: t.name,
                subtitle: `${t.client_name || t.organisation_name || 'Organisation'} • ${t.fields?.length || 0} fields`,
              })
            );
        }

        if (cardData.status === 'fulfilled' && cardData.value?.results) {
          cardData.value.results.forEach((c) =>
            combined.push({
              type: 'ID Card',
              id: c.id,
              tableId: c.table_id,
              status: c.status,
              title: c.title || `Card #${c.id}`,
              subtitle: `${c.subtitle || c.table_name || 'Card'} (${c.status_display || c.status || ''})`,
            })
          );
        }
      } catch (err) {
        console.warn('Global search error:', err);
      }
      setResults(combined.slice(0, 20));
      setLoading(false);
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  const handleSelectResult = (res) => {
    onClose();
    if (!onNavigate) return;
    if (res.type === 'ID Card') {
      onNavigate('idcard-actions', { tableId: res.tableId, status: res.status });
    } else if (res.type === 'Table') {
      onNavigate('idcard-actions', { tableId: res.id, status: 'pending' });
    } else if (res.type === 'Organisation') {
      onNavigate('cards', { clientId: res.id, org: res.raw });
    }
  };

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
          placeholder="Search organisations, tables, cards, names or emails…"
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
              key={`${res.type}-${res.id || idx}`}
              value={`${res.type}-${res.title}-${idx}`}
              style={S.item}
              onSelect={() => handleSelectResult(res)}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#1e3a8a';
                e.currentTarget.style.borderColor = '#3b82f6';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = '#0f172a';
                e.currentTarget.style.borderColor = '#334155';
              }}
            >
              <div style={S.icon(res.type)}>
                {res.type === 'Organisation' ? (
                  <Building size={16} color="#60a5fa" />
                ) : res.type === 'Table' ? (
                  <Table2 size={16} color="#fb923c" />
                ) : (
                  <CreditCard size={16} color="#34d399" />
                )}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {res.title}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {res.subtitle}
                </div>
              </div>
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: '#cbd5e1',
                  flexShrink: 0,
                }}
              >
                {res.type}
              </span>
            </Command.Item>
          ))}
        </Command.List>
      </Command>
    </div>
  );
}
