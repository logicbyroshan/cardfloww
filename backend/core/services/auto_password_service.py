"""
Auto Password & Unique Username Service

Handles:
1. Auto-generating PIN / temporary passwords:
   - If phone number is provided, uses the phone number as password.
   - If phone number is NOT provided, auto-generates an 8 to 10 character password from the
     organisation/user name shortform + special char + 4-digit random number (e.g., AIPS@4829, ADAR#7291).
2. Auto-generating clean, unique usernames from user input or email prefix.
3. Managing temporary password assignment, status tracking, and reset utilities.
"""
import re
import secrets
from typing import Optional
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


class AutoPasswordService:
    """Service for auto-generating temporary passwords and unique usernames."""

    SPECIAL_CHARS = ['@', '#', '$', '!']

    @classmethod
    def generate_auto_password(cls, name_or_org: str, phone: str = '') -> str:
        """
        Auto-generate a secure PIN / temporary password:
        - If phone is given (has digits >= 6), returns normalized phone digits.
        - If phone is NOT given, generates an 8 to 10 character password based on the
          organisation / user name acronym (max 4 chars) + special char + 4-digit random number.
        
        Examples:
          "Apex International Public School" -> "AIPS@4829" (9 chars)
          "Adarsh Vidya Mandir" -> "AVM@5182" (8 chars)
          "Card Flow" -> "CAFL@4921" (9 chars)
          "Adarsh" -> "ADAR#7321" (9 chars)
          "Apex" -> "APEX@6104" (9 chars)
        """
        # 1. If phone is provided and has enough digits, use phone
        clean_phone = re.sub(r'[^\d+]', '', str(phone or '').strip())
        phone_digits = re.sub(r'[^\d]', '', clean_phone)
        if len(phone_digits) >= 6:
            return clean_phone

        # 2. Derive shortform from name_or_org
        cleaned_name = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(name_or_org or '').strip())
        words = [w for w in cleaned_name.split() if w]

        shortform = ''
        if len(words) >= 3:
            # First letter of up to 4 words (e.g. AIPS, AVM)
            shortform = ''.join(w[0] for w in words[:4]).upper()
        elif len(words) == 2:
            # 2 words: take first 2 letters of each word (e.g. Card Flow -> CAFL)
            w1 = words[0][:2]
            w2 = words[1][:2]
            shortform = (w1 + w2).upper()
        elif len(words) == 1:
            # 1 word: take first 4 letters (or pad)
            w = words[0][:4]
            shortform = w.upper()
        
        # Ensure shortform is clean uppercase alphanumeric
        shortform = re.sub(r'[^A-Z0-9]', '', shortform)
        if len(shortform) < 3:
            shortform = (shortform + 'CARD')[:4]
        elif len(shortform) > 4:
            shortform = shortform[:4]

        special_char = secrets.choice(cls.SPECIAL_CHARS)
        random_num = secrets.randbelow(9000) + 1000  # 1000 to 9999 (4 digits)

        generated_pwd = f"{shortform}{special_char}{random_num}"
        return generated_pwd

    @classmethod
    def generate_unique_username(
        cls,
        email: str,
        preferred_username: str = '',
        name: str = '',
        exclude_user_id: Optional[int] = None,
    ) -> str:
        """
        Derive or sanitize a unique username:
        - If preferred_username is provided, sanitizes it and checks uniqueness.
        - If not provided, derives from email prefix (e.g. "admin@org.com" -> "admin").
        - Ensures uniqueness in the User table by appending incremental numeric suffixes if taken.
        """
        raw_seed = ''
        if preferred_username and str(preferred_username).strip():
            raw_seed = str(preferred_username).strip()
        elif email and '@' in str(email):
            raw_seed = str(email).split('@')[0].strip()
        elif name and str(name).strip():
            raw_seed = str(name).strip()
        else:
            raw_seed = f"user_{secrets.token_hex(3)}"

        # Sanitize seed to lowercase alphanumeric, underscore, hyphen, or dot
        clean_seed = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', raw_seed.lower()).strip('._-')
        if not clean_seed:
            clean_seed = f"user_{secrets.token_hex(3)}"

        candidate = clean_seed
        counter = 1

        qs = User.objects.all()
        if exclude_user_id:
            qs = qs.exclude(pk=exclude_user_id)

        while qs.filter(username__iexact=candidate).exists():
            candidate = f"{clean_seed}_{counter}"
            counter += 1

        return candidate

    @classmethod
    def assign_temp_password(cls, user, password: str, must_change: bool = True) -> None:
        """
        Assign password to user, record plaintext temp_password and metadata,
        and save user model.
        """
        user.set_password(password)
        user.temp_password = password
        user.temp_password_created_at = timezone.now()
        user.must_change_password = bool(must_change)
        user.save(update_fields=['password', 'temp_password', 'temp_password_created_at', 'must_change_password'])

    @classmethod
    def clear_temp_password(cls, user) -> None:
        """
        Called when a user sets their own password to clear the plaintext temp password.
        """
        user.temp_password = ''
        user.must_change_password = False
        user.save(update_fields=['temp_password', 'must_change_password'])
