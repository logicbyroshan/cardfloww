import React, { useEffect } from 'react';
import { Command } from 'cmdk';
import { Building, Table2 } from 'lucide-react';
import { clientApi } from '../../services/api';

// Styles for the cmdk Command container — visually identical to the old modal
const cmdkStyles = {
  overlay: {
    position: 'fixed', inset: 0, zIndex: 9999,
    background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)',
    display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
    paddingTop: '10vh',
  },
  panel: {
    width: '580px', maxHeight: '80vh', overflow: 'hidden',
    background: '#ffffff', borderRadius: '12px',
    boxShadow: '0 20px 40px rgba(0,0,0,0.2)',
    display: 'flex', flexDirection: 'column',
  },
  input: {
    width: '100%', padding: '1rem 1.25rem', border: 'none',
    borderBottom: '1px solid #e2e8f0', outline: 'none',
    fontSize: '1rem', fontFamily: 'inherit', color: '#0f172a',
    background: 'transparent', boxSizing: 'border-box',
  },
  list: {
    overflowY: 'auto', maxHeight: '350px', padding: '0.5rem',
    display: 'flex', flexDirection: 'column', gap: '4px',
  },
  empty: {
    padding: '20px', textAlign: 'center', color: '#94a3b8', fontSize: '13px',
  },
  item: {
    display: 'flex', alignItems: 'center', gap: '0.85rem',
    padding: '0.75rem 1rem', borderRadius: '8px',
    background: '#f8fafc', border: '1px solid #f1f5f9',
    cursor: 'pointer', transition: 'background 0.12s ease',
    outline: 'none',
  },
  itemSelected: {
    background: '#eff6ff', border: '1px solid #bfdbfe',
  },
  icon: (type) => ({
    width: '32px', height: '32px', borderRadius: '6px', flexShrink: 0,
    background: type === 'Organisation' ? '#dbeafe' : '#fef3c7',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  }),
};

export default function GlobalSearchModal({ isOpen, onClose }) {
  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div style={cmdkStyles.overlay} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <Command
        style={cmdkStyles.panel}
        shouldFilter={false}
        label="Global Search"
      >
        <Command.Input
          style={cmdkStyles.input}
          placeholder="Type to search organisations, tables, cards, or emails..."
          autoFocus
        />
        <CommandResults onClose={onClose} />
      </Command>
    </div>
  );
}

function CommandResults({ onClose }) {
  const [query, setQuery] = React.useState('');
  const [results, setResults] = React.useState([]);
  const [loading, setLoading] = React.useState(false);

  // Sync with cmdk Command.Input value via mutation observer
  // cmdk exposes value via its own state — wire it through useEffect
  const inputRef = React.useRef(null);

  React.useEffect(() => {
    const el = document.querySelector('[cmdk-input]');
    if (!el) return;
    const handler = () => setQuery(el.value);
    el.addEventListener('input', handler);
    return () => el.removeEventListener('input', handler);
  }, []);

  React.useEffect(() => {
    if (!query.trim()) { setResults([]); setLoading(false); return; }
    const q = query.toLowerCase().trim();
    setLoading(true);
    const timer = setTimeout(async () => {
      let combined = [];
      try {
        const data = await clientApi.getActive({ search: query, page_size: 10 });
        const list = Array.isArray(data?.clients) ? data.clients : Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : [];
        list.forEach(c => combined.push({ type: 'Organisation', title: c.name || 'Organisation', subtitle: `${c.email || ''} • ${c.phone || ''} (${c.status || 'active'})` }));
      } catch {}
      try {
        const local = JSON.parse(localStorage.getItem('cf_custom_clients') || '[]');
        local.filter(c => c.name?.toLowerCase().includes(q) || c.email?.toLowerCase().includes(q))
          .forEach(c => { if (!combined.some(x => x.title === c.name)) combined.push({ type: 'Organisation', title: c.name, subtitle: `${c.email || ''} • ${c.phone || ''} (active)` }); });
      } catch {}
      try {
        const localTbls = JSON.parse(localStorage.getItem('cf_custom_tables') || '[]');
        localTbls.filter(t => t.name?.toLowerCase().includes(q) || t.client_name?.toLowerCase().includes(q))
          .forEach(t => combined.push({ type: 'Table', title: t.name, subtitle: `${t.client_name || 'Organisation'} • ${t.fields?.length || 0} fields` }));
      } catch {}
      setResults(combined.slice(0, 15));
      setLoading(false);
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  return (
    <Command.List style={cmdkStyles.list}>
      {loading && <Command.Loading><div style={cmdkStyles.empty}>Searching...</div></Command.Loading>}
      <Command.Empty style={cmdkStyles.empty}>
        {query ? `No results found for "${query}"` : 'Start typing to search across the entire system'}
      </Command.Empty>
      {results.map((res, idx) => (
        <Command.Item
          key={idx}
          value={`${res.type}-${res.title}-${idx}`}
          style={cmdkStyles.item}
          onSelect={() => onClose()}
          onMouseEnter={e => Object.assign(e.currentTarget.style, cmdkStyles.itemSelected)}
          onMouseLeave={e => { e.currentTarget.style.background = '#f8fafc'; e.currentTarget.style.border = '1px solid #f1f5f9'; }}
        >
          <div style={cmdkStyles.icon(res.type)}>
            {res.type === 'Organisation' ? <Building size={16} color="#2563eb" /> : <Table2 size={16} color="#d97706" />}
          </div>
          <div>
            <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#1e293b' }}>{res.title}</div>
            <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{res.subtitle}</div>
          </div>
        </Command.Item>
      ))}
    </Command.List>
  );
}
