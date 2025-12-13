"""
SendBaba Email Validation & Auto-Correction Module
===================================================
- Validates email format
- Auto-corrects common typos (gmail.con -> gmail.com)
- Filters disposable/invalid domains
- Checks MX records (optional)
"""
import re
import dns.resolver
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

# Domain typo corrections
DOMAIN_CORRECTIONS = {
    'gmail.con': 'gmail.com', 'gmail.co': 'gmail.com', 'gmail.cm': 'gmail.com',
    'gmail.om': 'gmail.com', 'gmail.cpm': 'gmail.com', 'gmail.vom': 'gmail.com',
    'gmail.xom': 'gmail.com', 'gmail.c0m': 'gmail.com', 'gmail.comm': 'gmail.com',
    'gmai.com': 'gmail.com', 'gmial.com': 'gmail.com', 'gmal.com': 'gmail.com',
    'gmil.com': 'gmail.com', 'gmali.com': 'gmail.com', 'gamil.com': 'gmail.com',
    'gnail.com': 'gmail.com', 'gmaill.com': 'gmail.com', 'gimail.com': 'gmail.com',
    'gemail.com': 'gmail.com', 'gmsil.com': 'gmail.com', 'gmqil.com': 'gmail.com',
    'gmeil.com': 'gmail.com', 'gmaul.com': 'gmail.com', 'gmaol.com': 'gmail.com',
    'yahoo.con': 'yahoo.com', 'yahoo.co': 'yahoo.com', 'yahoo.cm': 'yahoo.com',
    'yahoo.om': 'yahoo.com', 'yahoo.cpm': 'yahoo.com', 'yaho.com': 'yahoo.com',
    'yahooo.com': 'yahoo.com', 'yhoo.com': 'yahoo.com', 'yhaoo.com': 'yahoo.com',
    'hotmail.con': 'hotmail.com', 'hotmail.co': 'hotmail.com', 'hotmail.cm': 'hotmail.com',
    'hotmal.com': 'hotmail.com', 'hotmai.com': 'hotmail.com', 'hotmial.com': 'hotmail.com',
    'hotamil.com': 'hotmail.com', 'hotmaill.com': 'hotmail.com', 'hitmail.com': 'hotmail.com',
    'outlook.con': 'outlook.com', 'outlook.co': 'outlook.com', 'outloo.com': 'outlook.com',
    'outlok.com': 'outlook.com', 'outlool.com': 'outlook.com',
    'icloud.con': 'icloud.com', 'icloud.co': 'icloud.com', 'icould.com': 'icloud.com',
    'aol.con': 'aol.com', 'aol.co': 'aol.com', 'aoll.com': 'aol.com',
    'live.con': 'live.com', 'live.co': 'live.com', 'livee.com': 'live.com',
    'ymail.con': 'ymail.com', 'ymail.co': 'ymail.com',
    'mail.con': 'mail.com', 'mail.co': 'mail.com',
}

# TLD corrections
TLD_CORRECTIONS = {
    'con': 'com', 'cpm': 'com', 'coom': 'com', 'comm': 'com', 'ocm': 'com',
    'vom': 'com', 'xom': 'com', 'c0m': 'com', 'cm': 'com', 'om': 'com',
    'cim': 'com', 'clm': 'com', 'cmo': 'com', 'comn': 'com', 'coim': 'com',
    'ney': 'net', 'nte': 'net', 'nett': 'net', 'ne': 'net', 'met': 'net',
    'ogr': 'org', 'or': 'org', 'orgg': 'org', 'prg': 'org', 'orf': 'org',
}

# Valid TLDs
VALID_TLDS = {
    'com', 'net', 'org', 'edu', 'gov', 'mil', 'int', 'info', 'biz', 'name', 'pro',
    'app', 'blog', 'cloud', 'dev', 'email', 'online', 'shop', 'site', 'store', 'tech',
    'website', 'work', 'xyz', 'io', 'co', 'me', 'tv', 'cc', 'ws', 'bz', 'ai', 'gg',
    'ac', 'ad', 'ae', 'af', 'ag', 'al', 'am', 'ao', 'ar', 'as', 'at', 'au', 'aw',
    'az', 'ba', 'bb', 'bd', 'be', 'bf', 'bg', 'bh', 'bi', 'bj', 'bm', 'bn', 'bo',
    'br', 'bs', 'bt', 'bw', 'by', 'ca', 'cd', 'cf', 'cg', 'ch', 'ci', 'ck', 'cl',
    'cn', 'cr', 'cu', 'cv', 'cw', 'cx', 'cy', 'cz', 'de', 'dj', 'dk', 'dm', 'do',
    'dz', 'ec', 'ee', 'eg', 'er', 'es', 'et', 'eu', 'fi', 'fj', 'fk', 'fm', 'fo',
    'fr', 'ga', 'gb', 'gd', 'ge', 'gf', 'gh', 'gi', 'gl', 'gm', 'gn', 'gp', 'gq',
    'gr', 'gt', 'gu', 'gw', 'gy', 'hk', 'hm', 'hn', 'hr', 'ht', 'hu', 'id', 'ie',
    'il', 'im', 'in', 'iq', 'ir', 'is', 'it', 'je', 'jm', 'jo', 'jp', 'ke', 'kg',
    'kh', 'ki', 'km', 'kn', 'kp', 'kr', 'kw', 'ky', 'kz', 'la', 'lb', 'lc', 'li',
    'lk', 'lr', 'ls', 'lt', 'lu', 'lv', 'ly', 'ma', 'mc', 'md', 'mg', 'mh', 'mk',
    'ml', 'mm', 'mn', 'mo', 'mp', 'mq', 'mr', 'ms', 'mt', 'mu', 'mv', 'mw', 'mx',
    'my', 'mz', 'na', 'nc', 'ne', 'nf', 'ng', 'ni', 'nl', 'no', 'np', 'nr', 'nu',
    'nz', 'pa', 'pe', 'pf', 'pg', 'ph', 'pk', 'pl', 'pm', 'pn', 'pr', 'ps', 'pt',
    'pw', 'py', 'qa', 're', 'ro', 'rs', 'ru', 'rw', 'sa', 'sb', 'sc', 'sd', 'se',
    'sg', 'sh', 'si', 'sk', 'sl', 'sm', 'sn', 'so', 'sr', 'ss', 'st', 'sv', 'sx',
    'sy', 'sz', 'tc', 'td', 'tf', 'tg', 'th', 'tj', 'tk', 'tl', 'tm', 'tn', 'to',
    'tr', 'tt', 'tw', 'tz', 'ua', 'ug', 'uk', 'us', 'uy', 'uz', 'va', 'vc', 've',
    'vg', 'vi', 'vn', 'vu', 'wf', 'ye', 'yt', 'za', 'zm', 'zw',
    'academy', 'agency', 'business', 'cafe', 'center', 'club', 'company', 'design',
    'digital', 'email', 'expert', 'farm', 'foundation', 'group', 'guru', 'help',
    'life', 'link', 'live', 'market', 'media', 'network', 'news', 'one', 'photo',
    'plus', 'press', 'pro', 'services', 'social', 'solutions', 'space', 'studio',
    'support', 'systems', 'team', 'technology', 'tips', 'today', 'tools', 'top',
    'training', 'video', 'world', 'zone'
}

# Disposable domains
DISPOSABLE_DOMAINS = {
    'mailinator.com', 'guerrillamail.com', 'tempmail.com', 'throwaway.com',
    '10minutemail.com', 'temp-mail.org', 'fakeinbox.com', 'sharklasers.com',
    'spam4.me', 'grr.la', 'guerrillamailblock.com', 'pokemail.net', 'spam.com',
    'trash.com', 'nospam.com', 'junk.com', 'mailnesia.com', 'yopmail.com',
    'example.com', 'test.com', 'localhost', 'invalid.com'
}

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def clean_email(email):
    """Clean and normalize email"""
    if not email or not isinstance(email, str):
        return None
    email = email.strip().lower()
    email = email.replace(' ', '').replace('\t', '').replace('\n', '')
    email = email.replace('"', '').replace("'", '').replace('<', '').replace('>', '')
    email = email.replace('@@', '@').replace(',,', '.').replace('..', '.')
    return email if email else None


def fix_email_typos(email):
    """Auto-correct common email typos. Returns (corrected_email, was_corrected)"""
    if not email:
        return email, False
    
    original = email
    email = clean_email(email)
    
    if not email or '@' not in email:
        return original, False
    
    try:
        local_part, domain = email.rsplit('@', 1)
        
        # Check full domain correction
        if domain in DOMAIN_CORRECTIONS:
            return f"{local_part}@{DOMAIN_CORRECTIONS[domain]}", True
        
        # Check TLD correction
        if '.' in domain:
            parts = domain.rsplit('.', 1)
            if len(parts) == 2:
                domain_name, tld = parts
                if tld in TLD_CORRECTIONS:
                    corrected = f"{local_part}@{domain_name}.{TLD_CORRECTIONS[tld]}"
                    return corrected, True
        
        return email, email != original
    except:
        return original, False


def get_domain(email):
    """Extract domain from email"""
    try:
        return email.split('@')[1].lower()
    except:
        return None


def get_tld(email):
    """Extract TLD from email"""
    try:
        domain = get_domain(email)
        return domain.split('.')[-1].lower() if domain else None
    except:
        return None


@lru_cache(maxsize=10000)
def has_mx_record(domain):
    """Check if domain has MX records"""
    try:
        mx_records = dns.resolver.resolve(domain, 'MX', lifetime=5)
        return len(list(mx_records)) > 0
    except:
        return False


def validate_email(email, check_mx=False, auto_fix=True):
    """
    Validate email with optional auto-correction.
    Returns: (is_valid, corrected_email, reason)
    """
    if not email:
        return False, None, 'empty'
    
    email = clean_email(email)
    if not email:
        return False, None, 'invalid_characters'
    
    # Auto-fix typos
    if auto_fix:
        email, _ = fix_email_typos(email)
    
    # Format check
    if not EMAIL_REGEX.match(email):
        return False, email, 'invalid_format'
    
    # TLD check
    tld = get_tld(email)
    if not tld or tld not in VALID_TLDS:
        return False, email, f'invalid_tld:{tld}'
    
    # Disposable check
    domain = get_domain(email)
    if domain in DISPOSABLE_DOMAINS:
        return False, email, 'disposable_domain'
    
    # Local part check
    local_part = email.split('@')[0]
    if len(local_part) < 1 or len(local_part) > 64:
        return False, email, 'invalid_local_part'
    
    # MX check
    if check_mx and not has_mx_record(domain):
        return False, email, 'no_mx_record'
    
    return True, email, None


def process_email_list(emails, check_mx=False, auto_fix=True):
    """Process list of emails: validate, correct, filter"""
    valid, invalid, corrected = [], [], []
    seen = set()
    
    for orig in emails:
        if not orig:
            continue
        is_valid, processed, reason = validate_email(orig, check_mx, auto_fix)
        
        if is_valid:
            if processed not in seen:
                seen.add(processed)
                valid.append(processed)
                orig_clean = clean_email(orig)
                if orig_clean != processed:
                    corrected.append({'original': orig_clean, 'corrected': processed})
        else:
            invalid.append({'email': orig, 'reason': reason})
    
    return {
        'valid': valid,
        'invalid': invalid,
        'corrected': corrected,
        'stats': {
            'total': len(emails),
            'valid': len(valid),
            'invalid': len(invalid),
            'corrected': len(corrected)
        }
    }


def quick_validate(email):
    """Fast validation without MX check"""
    is_valid, _, _ = validate_email(email, check_mx=False, auto_fix=False)
    return is_valid


def quick_fix(email):
    """Quick fix typos only"""
    email = clean_email(email)
    if email:
        corrected, _ = fix_email_typos(email)
        return corrected
    return email


# Legacy compatibility
def is_valid_email_format(email):
    return quick_validate(email)

def filter_valid_emails(emails, check_mx=False):
    result = process_email_list(emails, check_mx)
    return result['valid'], result['invalid']

def is_valid_tld(email):
    tld = get_tld(email)
    return tld in VALID_TLDS if tld else False

def is_disposable_domain(email):
    domain = get_domain(email)
    return domain in DISPOSABLE_DOMAINS if domain else True
