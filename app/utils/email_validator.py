"""
Email Validation Module for SendBaba
Filters invalid emails BEFORE sending to reduce bounce rate
"""
import re
import dns.resolver
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

# Valid TLDs (most common - expand as needed)
VALID_TLDS = {
    # Generic TLDs
    'com', 'net', 'org', 'edu', 'gov', 'mil', 'int', 'info', 'biz', 'name', 'pro',
    'aero', 'asia', 'cat', 'coop', 'jobs', 'mobi', 'museum', 'tel', 'travel', 'xxx',
    'app', 'blog', 'cloud', 'dev', 'email', 'online', 'shop', 'site', 'store', 'tech',
    'website', 'work', 'xyz', 'io', 'co', 'me', 'tv', 'cc', 'ws', 'bz', 'ai', 'gg',
    
    # Country TLDs
    'ac', 'ad', 'ae', 'af', 'ag', 'al', 'am', 'ao', 'aq', 'ar', 'as', 'at', 'au',
    'aw', 'ax', 'az', 'ba', 'bb', 'bd', 'be', 'bf', 'bg', 'bh', 'bi', 'bj', 'bm',
    'bn', 'bo', 'br', 'bs', 'bt', 'bw', 'by', 'ca', 'cd', 'cf', 'cg', 'ch', 'ci',
    'ck', 'cl', 'cm', 'cn', 'cr', 'cu', 'cv', 'cw', 'cx', 'cy', 'cz', 'de', 'dj',
    'dk', 'dm', 'do', 'dz', 'ec', 'ee', 'eg', 'er', 'es', 'et', 'eu', 'fi', 'fj',
    'fk', 'fm', 'fo', 'fr', 'ga', 'gb', 'gd', 'ge', 'gf', 'gg', 'gh', 'gi', 'gl',
    'gm', 'gn', 'gp', 'gq', 'gr', 'gt', 'gu', 'gw', 'gy', 'hk', 'hm', 'hn', 'hr',
    'ht', 'hu', 'id', 'ie', 'il', 'im', 'in', 'iq', 'ir', 'is', 'it', 'je', 'jm',
    'jo', 'jp', 'ke', 'kg', 'kh', 'ki', 'km', 'kn', 'kp', 'kr', 'kw', 'ky', 'kz',
    'la', 'lb', 'lc', 'li', 'lk', 'lr', 'ls', 'lt', 'lu', 'lv', 'ly', 'ma', 'mc',
    'md', 'me', 'mg', 'mh', 'mk', 'ml', 'mm', 'mn', 'mo', 'mp', 'mq', 'mr', 'ms',
    'mt', 'mu', 'mv', 'mw', 'mx', 'my', 'mz', 'na', 'nc', 'ne', 'nf', 'ng', 'ni',
    'nl', 'no', 'np', 'nr', 'nu', 'nz', 'om', 'pa', 'pe', 'pf', 'pg', 'ph', 'pk',
    'pl', 'pm', 'pn', 'pr', 'ps', 'pt', 'pw', 'py', 'qa', 're', 'ro', 'rs', 'ru',
    'rw', 'sa', 'sb', 'sc', 'sd', 'se', 'sg', 'sh', 'si', 'sk', 'sl', 'sm', 'sn',
    'so', 'sr', 'ss', 'st', 'sv', 'sx', 'sy', 'sz', 'tc', 'td', 'tf', 'tg', 'th',
    'tj', 'tk', 'tl', 'tm', 'tn', 'to', 'tr', 'tt', 'tw', 'tz', 'ua', 'ug', 'uk',
    'us', 'uy', 'uz', 'va', 'vc', 've', 'vg', 'vi', 'vn', 'vu', 'wf', 'ws', 'ye',
    'yt', 'za', 'zm', 'zw',
    
    # New gTLDs (common ones)
    'academy', 'accountant', 'actor', 'agency', 'apartments', 'associates', 'attorney',
    'auction', 'band', 'bank', 'bar', 'beer', 'best', 'bid', 'bike', 'bingo', 'black',
    'blue', 'boutique', 'broker', 'builders', 'business', 'cab', 'cafe', 'camera',
    'camp', 'capital', 'cards', 'care', 'career', 'careers', 'cash', 'casino', 'catering',
    'center', 'chat', 'cheap', 'church', 'city', 'claims', 'cleaning', 'click', 'clinic',
    'clothing', 'club', 'coach', 'codes', 'coffee', 'college', 'community', 'company',
    'computer', 'condos', 'construction', 'consulting', 'contractors', 'cooking', 'cool',
    'country', 'coupons', 'courses', 'credit', 'creditcard', 'cricket', 'cruises', 'dance',
    'date', 'dating', 'deals', 'degree', 'delivery', 'democrat', 'dental', 'dentist',
    'design', 'diamonds', 'diet', 'digital', 'direct', 'directory', 'discount', 'doctor',
    'dog', 'domains', 'download', 'education', 'energy', 'engineer', 'engineering',
    'enterprises', 'equipment', 'estate', 'events', 'exchange', 'expert', 'exposed',
    'express', 'fail', 'faith', 'family', 'fan', 'fans', 'farm', 'fashion', 'film',
    'finance', 'financial', 'fish', 'fishing', 'fit', 'fitness', 'flights', 'florist',
    'flowers', 'football', 'forex', 'forsale', 'foundation', 'fun', 'fund', 'furniture',
    'futbol', 'fyi', 'gallery', 'game', 'games', 'garden', 'gift', 'gifts', 'gives',
    'glass', 'global', 'gold', 'golf', 'gmbh', 'graphics', 'gratis', 'green', 'gripe',
    'group', 'guide', 'guru', 'healthcare', 'help', 'hockey', 'holdings', 'holiday',
    'horse', 'hospital', 'host', 'hosting', 'house', 'how', 'immo', 'immobilien',
    'industries', 'ink', 'institute', 'insure', 'international', 'investments', 'irish',
    'jetzt', 'jewelry', 'kim', 'kitchen', 'land', 'lawyer', 'lease', 'legal', 'lgbt',
    'life', 'lighting', 'limited', 'limo', 'link', 'live', 'loan', 'loans', 'lol',
    'lotto', 'love', 'ltd', 'luxury', 'maison', 'management', 'market', 'marketing',
    'markets', 'mba', 'media', 'memorial', 'men', 'menu', 'miami', 'moda', 'money',
    'mortgage', 'movie', 'network', 'news', 'ninja', 'one', 'onl', 'ooo', 'organic',
    'partners', 'parts', 'party', 'pet', 'pharmacy', 'photo', 'photography', 'photos',
    'pics', 'pictures', 'pink', 'pizza', 'place', 'plumbing', 'plus', 'poker', 'porn',
    'press', 'productions', 'promo', 'properties', 'property', 'protection', 'pub',
    'racing', 'realestate', 'realty', 'recipes', 'red', 'rehab', 'reise', 'reisen',
    'rent', 'rentals', 'repair', 'report', 'republican', 'rest', 'restaurant', 'review',
    'reviews', 'rich', 'rip', 'rocks', 'rodeo', 'run', 'sale', 'salon', 'sarl', 'school',
    'schule', 'science', 'security', 'services', 'sex', 'sexy', 'shiksha', 'shoes',
    'show', 'singles', 'ski', 'soccer', 'social', 'software', 'solar', 'solutions',
    'space', 'sport', 'sports', 'spot', 'srl', 'storage', 'stream', 'studio', 'study',
    'style', 'sucks', 'supplies', 'supply', 'support', 'surgery', 'systems', 'tax',
    'taxi', 'team', 'technology', 'tennis', 'theater', 'theatre', 'tickets', 'tips',
    'tires', 'today', 'tools', 'top', 'tours', 'town', 'toys', 'trade', 'trading',
    'training', 'tube', 'university', 'vacations', 'ventures', 'vet', 'viajes', 'video',
    'villas', 'vin', 'vip', 'vision', 'vodka', 'vote', 'voting', 'voyage', 'watch',
    'webcam', 'wedding', 'wiki', 'win', 'wine', 'winners', 'world', 'wtf', 'yoga',
    'zone'
}

# Known invalid/spam domains
INVALID_DOMAINS = {
    'example.com', 'test.com', 'localhost', 'invalid.com', 'fake.com',
    'mailinator.com', 'guerrillamail.com', 'tempmail.com', 'throwaway.com',
    '10minutemail.com', 'temp-mail.org', 'fakeinbox.com', 'sharklasers.com',
    'spam4.me', 'grr.la', 'guerrillamailblock.com', 'pokemail.net',
    'spam.com', 'trash.com', 'nospam.com', 'junk.com'
}

# Regex for basic email format
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)

# Common typos in domain extensions
TYPO_CORRECTIONS = {
    'con': 'com',
    'cpm': 'com',
    'coom': 'com',
    'comm': 'com',
    'ocm': 'com',
    'vom': 'com',
    'xom': 'com',
    'c0m': 'com',
    'cm': 'com',
    'om': 'com',
    'ney': 'net',
    'nte': 'net',
    'nett': 'net',
    'ne': 'net',
    'ogr': 'org',
    'or': 'org',
    'orgg': 'org',
    'gmai.com': 'gmail.com',
    'gmial.com': 'gmail.com',
    'gmail.co': 'gmail.com',
    'gmal.com': 'gmail.com',
    'gmil.com': 'gmail.com',
    'gamil.com': 'gmail.com',
    'hotmal.com': 'hotmail.com',
    'hotmai.com': 'hotmail.com',
    'hotmial.com': 'hotmail.com',
    'hotamil.com': 'hotmail.com',
    'yahooo.com': 'yahoo.com',
    'yaho.com': 'yahoo.com',
    'yhoo.com': 'yahoo.com',
    'yhaoo.com': 'yahoo.com',
}


def is_valid_email_format(email):
    """Check basic email format"""
    if not email or not isinstance(email, str):
        return False
    email = email.strip().lower()
    if len(email) > 254:  # Max email length
        return False
    return EMAIL_REGEX.match(email) is not None


def get_tld(email):
    """Extract TLD from email"""
    try:
        domain = email.split('@')[1]
        return domain.split('.')[-1].lower()
    except:
        return None


def get_domain(email):
    """Extract domain from email"""
    try:
        return email.split('@')[1].lower()
    except:
        return None


def is_valid_tld(email):
    """Check if TLD is valid"""
    tld = get_tld(email)
    if not tld:
        return False
    return tld in VALID_TLDS


def is_disposable_domain(email):
    """Check if domain is a known disposable/spam domain"""
    domain = get_domain(email)
    if not domain:
        return True
    return domain in INVALID_DOMAINS


@lru_cache(maxsize=10000)
def has_mx_record(domain):
    """Check if domain has MX records (cached)"""
    try:
        mx_records = dns.resolver.resolve(domain, 'MX', lifetime=5)
        return len(list(mx_records)) > 0
    except:
        return False


def validate_email(email, check_mx=False):
    """
    Comprehensive email validation
    Returns: (is_valid, error_reason)
    """
    if not email:
        return False, 'empty'
    
    email = email.strip().lower()
    
    # Basic format check
    if not is_valid_email_format(email):
        return False, 'invalid_format'
    
    # Check TLD
    if not is_valid_tld(email):
        tld = get_tld(email)
        return False, f'invalid_tld:{tld}'
    
    # Check for disposable domains
    if is_disposable_domain(email):
        return False, 'disposable_domain'
    
    # Check local part
    local_part = email.split('@')[0]
    if len(local_part) < 1:
        return False, 'empty_local_part'
    if '..' in local_part:
        return False, 'double_dots'
    
    # Optional MX check (expensive, use sparingly)
    if check_mx:
        domain = get_domain(email)
        if not has_mx_record(domain):
            return False, 'no_mx_record'
    
    return True, None


def filter_valid_emails(emails, check_mx=False):
    """
    Filter a list of emails, returning only valid ones
    Returns: (valid_emails, invalid_emails_with_reasons)
    """
    valid = []
    invalid = []
    
    for email in emails:
        is_valid, reason = validate_email(email, check_mx)
        if is_valid:
            valid.append(email)
        else:
            invalid.append({'email': email, 'reason': reason})
    
    return valid, invalid


def fix_common_typos(email):
    """Attempt to fix common email typos"""
    if not email:
        return email
    
    email = email.strip().lower()
    
    try:
        local, domain = email.split('@')
        
        # Check for full domain typos
        if domain in TYPO_CORRECTIONS:
            domain = TYPO_CORRECTIONS[domain]
        else:
            # Check TLD typos
            parts = domain.rsplit('.', 1)
            if len(parts) == 2:
                name, tld = parts
                if tld in TYPO_CORRECTIONS:
                    domain = f"{name}.{TYPO_CORRECTIONS[tld]}"
        
        return f"{local}@{domain}"
    except:
        return email


# Quick validation function for bulk use
def quick_validate(email):
    """Fast validation - just format and TLD check"""
    if not email or not isinstance(email, str):
        return False
    email = email.strip().lower()
    if not EMAIL_REGEX.match(email):
        return False
    tld = get_tld(email)
    return tld in VALID_TLDS
