import os
import sys
import re

# Set up Django environment
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir) if os.path.basename(script_dir) == 'scripts' else script_dir
sys.path.insert(0, root_dir)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.db import transaction
from django.contrib.auth import get_user_model
from assistants.models import Assistant
from organisation.models import Organisation
from tables.models import Table, IDCard

User = get_user_model()

ROMAN_MAPPING = {
    '12': ['12', 'XII'],
    '11': ['11', 'XI'],
    '10': ['10', 'X'],
    '9': ['9', 'IX'],
    '8': ['8', 'VIII'],
    '7': ['7', 'VII'],
    '6': ['6', 'VI'],
    '5': ['5', 'V'],
    '4': ['4', 'IV'],
    '3': ['3', 'III'],
    '2': ['2', 'II'],
    '1': ['1', 'I'],
}

def repair():
    print("Starting database repair and inspection for Assistants...")
    print("=" * 80)
    
    assistants = Assistant.objects.select_related('user', 'client').prefetch_related('assigned_groups').all()
    clients = list(Organisation.objects.select_related('user').all())
    
    print(f"Found {len(assistants)} Assistant(s) and {len(clients)} Organisation(s) in the database.\n")
    
    repaired_count = 0
    skipped_count = 0
    
    for ast in assistants:
        # Timezone-safe check for assistants created on migration day (July 3, 4, or 5 in UTC)
        # and ensure we only target the IPS clients we are repairing (email/username contains 'ips')
        email_lower = (ast.user.email or "").lower()
        username_lower = ast.user.username.lower()
        is_ips = 'ips' in email_lower or 'ips' in username_lower
        is_target_date = ast.created_at and ast.created_at.year == 2026 and ast.created_at.month == 7 and ast.created_at.day in (3, 4, 5)
        
        if not (is_ips and is_target_date):
            skipped_count += 1
            continue

        username = ast.user.username
        email = ast.user.email or ""
        name = ast.user.get_full_name() or username
        current_client_name = ast.client.name if ast.client else "None"
        
        print(f"Assistant: {name} (Email: {email})")
        print(f"  Current Client: {current_client_name} (ID: {ast.client_id})")
        
        # 1. Check and repair Client assignment
        target_client = ast.client
        client_changed = False
        
        # Calculate matching score for all clients to verify/re-assign
        best_client = None
        best_score = 0
        
        email_clean = email.lower().strip()
        email_domain = email_clean.split('@')[-1] if '@' in email_clean else ""
        domain_prefix = email_domain.split('.')[0] if email_domain else ""
        
        # We only try to match if domain prefix is not a common provider
        is_school_domain = domain_prefix and domain_prefix not in ('gmail', 'yahoo', 'outlook', 'hotmail', 'mail', 'live', 'icloud', 'protonmail', 'zoho', 'yandex')
        
        if is_school_domain:
            for c in clients:
                c_name = c.name.lower()
                c_user_email = (c.user.email or "").lower()
                
                score = 0
                # Perfect domain match
                if c_user_email and c_user_email.split('@')[-1] == email_domain:
                    score += 100
                
                # Check initials of the client name
                c_name_clean = re.sub(r'[^a-z0-9\s]', ' ', c_name)
                words = [w.strip() for w in c_name_clean.split() if w.strip()]
                initials = "".join([w[0] for w in words if w])
                
                if domain_prefix == initials:
                    score += 90
                elif domain_prefix in c_name:
                    score += 70
                else:
                    # Check if initials of a prefix match domain_prefix
                    for i in range(2, len(words) + 1):
                        sub_initials = "".join([w[0] for w in words[:i] if w])
                        if domain_prefix == sub_initials:
                            score += 80
                            break
                            
                # Check word inclusion
                matched_words = 0
                for w in words:
                    if len(w) >= 3 and w in domain_prefix:
                        matched_words += 1
                if matched_words > 0:
                    score += matched_words * 15
                    
                if score > best_score:
                    best_score = score
                    best_client = c

        # Determine if we should change/assign the client
        current_score = 0
        if target_client and is_school_domain:
            c_name = target_client.name.lower()
            c_name_clean = re.sub(r'[^a-z0-9\s]', ' ', c_name)
            words = [w.strip() for w in c_name_clean.split() if w.strip()]
            initials = "".join([w[0] for w in words if w])
            if domain_prefix == initials:
                current_score += 90
            elif domain_prefix in c_name:
                current_score += 70
            for w in words:
                if len(w) >= 3 and w in domain_prefix:
                    current_score += 15

        if best_client and best_score >= 30:
            if not target_client or (target_client.id != best_client.id and current_score < 30):
                print(f"  [Fix] Re-assigning Client: '{current_client_name}' (ID: {ast.client_id}) -> '{best_client.name}' (ID: {best_client.id}) [Match Score: {best_score}]")
                ast.client = best_client
                ast.save(update_fields=['client'])
                target_client = best_client
                current_client_name = best_client.name
                client_changed = True
        
        if not target_client:
            print("  [Error] No client found or matched for this assistant.")
            print("-" * 80)
            continue
            
        # 2. Check and repair class/section assignments
        if True:
            print("  Attempting to parse and restore class/section assignments...")
            
            # Remove acronym prefixes from name to isolate class part
            clean_name = name.strip()
            for prefix in ["IPS", "IPS Seoni", "IPS Bhopal", target_client.name]:
                if clean_name.lower().startswith(prefix.lower()):
                    clean_name = clean_name[len(prefix):].strip()
            
            # Try to match regex patterns
            parsed_class = None
            parsed_section = None
            
            # Pattern 1: "12B" or "10A" (Number followed by letter)
            m1 = re.match(r'^(\d+)([a-zA-Z])$', clean_name)
            # Pattern 2: "NIRMAAN-F" (Name followed by hyphen and letter)
            m2 = re.match(r'^([a-zA-Z\s]+)-([a-zA-Z])$', clean_name)
            # Pattern 3: "AARAMBH-A"
            m3 = re.match(r'^([a-zA-Z\s\d]+)-([a-zA-Z])$', clean_name)
            
            if m1:
                parsed_class = m1.group(1)
                parsed_section = m1.group(2)
            elif m2:
                parsed_class = m2.group(1).strip()
                parsed_section = m2.group(2)
            elif m3:
                parsed_class = m3.group(1).strip()
                parsed_section = m3.group(2)
            else:
                # Fallback: check email prefix
                email_prefix = email.split('@')[0]
                m_email = re.match(r'^([a-zA-Z\s\d]+)-([a-zA-Z])$', email_prefix)
                m_email_num = re.match(r'^(\d+)([a-zA-Z])$', email_prefix)
                if m_email:
                    parsed_class = m_email.group(1).strip()
                    parsed_section = m_email.group(2)
                elif m_email_num:
                    parsed_class = m_email_num.group(1)
                    parsed_section = m_email_num.group(2)
                else:
                    parsed_class = clean_name
            
            if parsed_class:
                print(f"  Parsed class: '{parsed_class}' | Parsed section: '{parsed_section}'")
                
                # Get groups that are student-related (must contain 'student' or 'STUDENT')
                student_groups = Table.objects.filter(client=target_client, name__icontains='student')
                if not student_groups.exists():
                    student_groups = Table.objects.filter(client=target_client)
                
                # Get all active tables under student groups
                tables = Table.objects.filter(group__in=student_groups, deleted_by_client=False)
                
                table_field_map = {}
                for table in tables:
                    class_field, section_field = None, None
                    for field in (table.fields or []):
                        ft = field.get('type', '').lower()
                        fn = field.get('name', '')
                        fn_lower = fn.lower()
                        if ft == 'class' or fn_lower == 'class' or 'class' in fn_lower or fn_lower in ('std', 'standard', 'grade'):
                            class_field = fn
                        elif ft == 'section' or fn_lower == 'section' or fn_lower == 'sec' or 'section' in fn_lower:
                            section_field = fn
                    table_field_map[table.id] = {
                        'table': table,
                        'class_field': class_field,
                        'section_field': section_field
                    }
                
                # Check for cards matching the class/section
                matched_table_ids = set()
                matched_classes = set()
                matched_sections = set()
                
                # Prepare case-insensitive target sets (including roman numerals and trailing spaces)
                class_vals = [parsed_class.lower(), parsed_class.upper()]
                if parsed_class in ROMAN_MAPPING:
                    for val in ROMAN_MAPPING[parsed_class]:
                        class_vals.append(val.lower())
                        class_vals.append(val.upper())
                
                # Append variations with leading/trailing spaces for Excel compatibility
                spaced_class_vals = []
                for val in class_vals:
                    spaced_class_vals.append(f" {val}")
                    spaced_class_vals.append(f"{val} ")
                    spaced_class_vals.append(f" {val} ")
                class_vals.extend(spaced_class_vals)
                class_vals = list(set(class_vals))
                
                section_vals = []
                if parsed_section:
                    section_vals = [parsed_section.lower(), parsed_section.upper()]
                    spaced_section_vals = []
                    for val in section_vals:
                        spaced_section_vals.append(f" {val}")
                        spaced_section_vals.append(f"{val} ")
                        spaced_section_vals.append(f" {val} ")
                    section_vals.extend(spaced_section_vals)
                    section_vals = list(set(section_vals))
                
                # 2a. Card Matching
                for t_id, t_info in table_field_map.items():
                    c_f = t_info['class_field']
                    s_f = t_info['section_field']
                    
                    if not c_f:
                        continue
                        
                    cards_qs = IDCard.objects.filter(table_id=t_id, deleted_at__isnull=True)
                    if c_f:
                        cards_qs = cards_qs.filter(**{f"field_data__{c_f}__in": class_vals})
                    if s_f and section_vals:
                        cards_qs = cards_qs.filter(**{f"field_data__{s_f}__in": section_vals})
                        
                    if cards_qs.exists():
                        matched_table_ids.add(t_id)
                        
                        sample_card = cards_qs.first()
                        actual_class = sample_card.field_data.get(c_f) if c_f else None
                        actual_section = sample_card.field_data.get(s_f) if s_f else None
                        
                        if actual_class:
                            matched_classes.add(str(actual_class).strip())
                        else:
                            matched_classes.add(parsed_class)
                            
                        if actual_section:
                            matched_sections.add(str(actual_section).strip())
                        elif parsed_section:
                            matched_sections.add(parsed_section)
                
                # 2b. Table Name Matching Fallback (if no cards matched)
                if not matched_table_ids:
                    for t_id, t_info in table_field_map.items():
                        c_f = t_info['class_field']
                        if not c_f:
                            continue
                        table = t_info['table']
                        t_name_clean = re.sub(r'[^a-zA-Z0-9]', ' ', table.name).lower()
                        t_words = t_name_clean.split()
                        
                        matches_class = False
                        for c_val in class_vals:
                            c_val_clean = c_val.strip().lower()
                            if c_val_clean in t_words or c_val_clean == "".join(t_words):
                                matches_class = True
                                break
                                
                        matches_section = True
                        if parsed_section:
                            matches_section = False
                            for s_val in section_vals:
                                s_val_clean = s_val.strip().lower()
                                if s_val_clean in t_words or s_val_clean == "".join(t_words):
                                    matches_section = True
                                    break
                                    
                        if matches_class and matches_section:
                            matched_table_ids.add(table.id)
                            matched_classes.add(parsed_class)
                            if parsed_section:
                                matched_sections.add(parsed_section)
                
                # Deduplicate and normalize representation to keep only the Roman numeral version if it exists
                cleaned_matched_classes = set()
                for c in matched_classes:
                    if c in ROMAN_MAPPING:
                        cleaned_matched_classes.add(ROMAN_MAPPING[c][-1])
                    else:
                        cleaned_matched_classes.add(c)
                matched_classes = cleaned_matched_classes
                
                matched_sections = {s.upper() for s in matched_sections}
                
                # 2c. Save Matches and Scopes
                if matched_classes:
                    print(f"  [Fix] Matches found! Assigning allowed_classes: {list(matched_classes)}, allowed_sections: {list(matched_sections)}")
                    ast.allowed_classes = list(matched_classes)
                    ast.allowed_sections = list(matched_sections)
                    
                    # Filter assigned groups to ONLY be from student groups
                    groups = Table.objects.filter(tables__id__in=matched_table_ids, id__in=student_groups).distinct()
                    ast.assigned_groups.set(groups)
                    
                    scopes = []
                    for group in groups:
                        group_table_ids = [t.id for t in group.tables.all() if t.id in matched_table_ids]
                        for t_id in group_table_ids:
                            table_name = table_field_map[t_id]['table'].name
                            
                            # Construct class_sections object mapping class name to lists of sections
                            class_sections = {}
                            for c in matched_classes:
                                class_sections[c] = list(matched_sections)
                                
                            scopes.append({
                                'scope_type': 'table',
                                'scope_id': t_id,
                                'scope_name': table_name,
                                'group_id': group.id,
                                'group_name': group.name,
                                'classes': list(matched_classes),
                                'sections': list(matched_sections),
                                'branches': [],
                                'class_sections': class_sections
                            })
                    
                    ast.assignment_scopes = scopes
                    ast.assigned_table_ids = list(matched_table_ids)
                    ast.save(update_fields=['allowed_classes', 'allowed_sections', 'assignment_scopes', 'assigned_table_ids'])
                    print(f"  [Success] Restored scope assignments and linked to {len(groups)} group(s).")
                    repaired_count += 1
                else:
                    print("  [Warning] No matching card or table records found in DB for this class/section. Clearing any legacy assignments.")
                    ast.allowed_classes = []
                    ast.allowed_sections = []
                    ast.assignment_scopes = []
                    ast.assigned_groups.clear()
                    ast.assigned_table_ids = []
                    ast.save(update_fields=['allowed_classes', 'allowed_sections', 'assignment_scopes', 'assigned_table_ids'])
                    repaired_count += 1
            else:
                print("  [Error] Could not parse class name from assistant name. Clearing legacy assignments.")
                ast.allowed_classes = []
                ast.allowed_sections = []
                ast.assignment_scopes = []
                ast.assigned_groups.clear()
                ast.assigned_table_ids = []
                ast.save(update_fields=['allowed_classes', 'allowed_sections', 'assignment_scopes', 'assigned_table_ids'])
                repaired_count += 1
                
        print("-" * 80)
        
    print(f"\nRepair complete. Repaired/Updated: {repaired_count} assistant(s). Skipped: {skipped_count} assistant(s).")

if __name__ == "__main__":
    repair()
