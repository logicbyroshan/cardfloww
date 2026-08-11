/**
 * formatters.js — Shared utility functions for formatting dates, strings, and numbers.
 */

/**
 * Formats an ISO date string or Date object into DD/MM/YY HH:MM format.
 * @param {string|Date} str
 * @returns {string}
 */
export const formatDT = (str) => {
  if (!str) return '—';
  try {
    const d = new Date(str);
    if (isNaN(d.getTime())) return String(str);
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = String(d.getFullYear()).slice(-2);
    const hours = String(d.getHours()).padStart(2, '0');
    const mins = String(d.getMinutes()).padStart(2, '0');
    return `${day}/${month}/${year} ${hours}:${mins}`;
  } catch {
    return String(str);
  }
};

/**
 * Formats a number with comma separators.
 * @param {number} num
 * @returns {string}
 */
export const formatNumber = (num) => {
  if (num === null || num === undefined || isNaN(num)) return '0';
  return Number(num).toLocaleString('en-IN');
};

/**
 * Capitalizes the first letter of a string.
 * @param {string} str
 * @returns {string}
 */
export const capitalize = (str) => {
  if (!str) return '';
  return String(str).charAt(0).toUpperCase() + String(str).slice(1).toLowerCase();
};
