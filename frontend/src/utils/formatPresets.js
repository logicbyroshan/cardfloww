/**
 * formatPresets.js
 * Standard format presets and option sets for Class, Section, Course, Branch, and Select dropdown columns.
 */

export const FORMAT_PRESETS = {
  class_roman: {
    id: 'class_roman',
    label: 'Roman (I, II, III... XII)',
    type: 'class',
    options: ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII'],
  },
  class_ordinal: {
    id: 'class_ordinal',
    label: 'Ordinal (1st, 2nd... 12th + Nursery)',
    type: 'class',
    options: [
      'Playgroup',
      'Nursery',
      'LKG',
      'UKG',
      '1st',
      '2nd',
      '3rd',
      '4th',
      '5th',
      '6th',
      '7th',
      '8th',
      '9th',
      '10th',
      '11th',
      '12th',
    ],
  },
  class_numeric: {
    id: 'class_numeric',
    label: 'Numeric (1, 2, 3... 12)',
    type: 'class',
    options: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12'],
  },
  class_words: {
    id: 'class_words',
    label: 'Words (First, Second... Twelfth)',
    type: 'class',
    options: [
      'First',
      'Second',
      'Third',
      'Fourth',
      'Fifth',
      'Sixth',
      'Seventh',
      'Eighth',
      'Ninth',
      'Tenth',
      'Eleventh',
      'Twelfth',
    ],
  },
  section_alpha: {
    id: 'section_alpha',
    label: 'Alphabets (A, B, C, D, E, F, G, H)',
    type: 'section',
    options: ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],
  },
  section_named: {
    id: 'section_named',
    label: 'House / Flower Names (Rose, Lotus, Jasmine...)',
    type: 'section',
    options: ['Rose', 'Lotus', 'Jasmine', 'Tulip', 'Lily', 'Sunflower', 'Daffodil', 'Marigold'],
  },
  section_prefixed: {
    id: 'section_prefixed',
    label: 'Prefixed (Sec-A, Sec-B, Sec-C, Sec-D)',
    type: 'section',
    options: ['Sec-A', 'Sec-B', 'Sec-C', 'Sec-D', 'Sec-E', 'Sec-F'],
  },
  course_higher: {
    id: 'course_higher',
    label: 'Standard Higher Ed (B.Tech, BCA, MCA, MBA...)',
    type: 'course',
    options: [
      'B.Tech',
      'M.Tech',
      'BCA',
      'MCA',
      'B.Sc',
      'M.Sc',
      'B.Com',
      'M.Com',
      'B.A',
      'M.A',
      'BBA',
      'MBA',
      'B.Ed',
      'Diploma',
      'Ph.D',
    ],
  },
  branch_eng: {
    id: 'branch_eng',
    label: 'Engineering / Tech Streams (CSE, ECE, ME, CE, IT...)',
    type: 'branch',
    options: [
      'CSE',
      'IT',
      'AI & ML',
      'Data Science',
      'ECE',
      'EE',
      'ME',
      'CE',
      'Chemical',
      'Biotech',
      'Cyber Security',
      'Commerce',
      'Science',
      'Arts',
    ],
  },
  custom: {
    id: 'custom',
    label: 'Custom Option List',
    type: 'custom',
    options: [],
  },
};

/**
 * Get the list of preset descriptors applicable for a field type.
 */
export function getPresetsForFieldType(fieldType = '') {
  const t = String(fieldType || '').toLowerCase().trim();
  if (t === 'class') {
    return [
      FORMAT_PRESETS.class_ordinal,
      FORMAT_PRESETS.class_roman,
      FORMAT_PRESETS.class_numeric,
      FORMAT_PRESETS.class_words,
      FORMAT_PRESETS.custom,
    ];
  }
  if (t === 'section') {
    return [
      FORMAT_PRESETS.section_alpha,
      FORMAT_PRESETS.section_named,
      FORMAT_PRESETS.section_prefixed,
      FORMAT_PRESETS.custom,
    ];
  }
  if (t === 'course') {
    return [FORMAT_PRESETS.course_higher, FORMAT_PRESETS.custom];
  }
  if (t === 'branch') {
    return [FORMAT_PRESETS.branch_eng, FORMAT_PRESETS.custom];
  }
  return Object.values(FORMAT_PRESETS);
}

/**
 * Resolve options array for a field definition.
 */
export function getOptionsForField(field) {
  if (!field) return [];
  if (Array.isArray(field.options) && field.options.length > 0) {
    return field.options.map((opt) => String(opt).trim()).filter(Boolean);
  }
  if (typeof field.options === 'string' && field.options.trim()) {
    return field.options
      .split(/[\n,]+/)
      .map((opt) => opt.trim())
      .filter(Boolean);
  }
  if (field.format_preset && FORMAT_PRESETS[field.format_preset]) {
    return FORMAT_PRESETS[field.format_preset].options;
  }

  const ftype = String(field.type || '').toLowerCase().trim();
  const fname = String(field.name || '').toLowerCase().trim();

  if (ftype === 'class' || fname === 'class' || fname.includes('class') || fname === 'std') {
    return FORMAT_PRESETS.class_ordinal.options;
  }
  if (ftype === 'section' || fname === 'section' || fname === 'sec' || fname === 'div') {
    return FORMAT_PRESETS.section_alpha.options;
  }
  if (ftype === 'course' || fname === 'course' || fname.includes('degree')) {
    return FORMAT_PRESETS.course_higher.options;
  }
  if (ftype === 'branch' || fname === 'branch' || fname.includes('stream') || fname === 'dept') {
    return FORMAT_PRESETS.branch_eng.options;
  }

  return [];
}

/**
 * Determine if a field should be rendered as a dropdown select.
 */
export function isDropdownField(field) {
  if (!field) return false;
  const ftype = String(field.type || '').toLowerCase().trim();
  const fname = String(field.name || '').toLowerCase().trim();

  if (['select', 'class', 'section', 'course', 'branch', 'class_section'].includes(ftype)) {
    return true;
  }
  if (Array.isArray(field.options) && field.options.length > 0) {
    return true;
  }
  if (typeof field.options === 'string' && field.options.trim().length > 0) {
    return true;
  }
  if (field.format_preset && field.format_preset !== 'custom') {
    return true;
  }
  if (fname === 'class' || fname === 'section' || fname === 'course' || fname === 'branch' || fname === 'gender') {
    return true;
  }
  return false;
}
