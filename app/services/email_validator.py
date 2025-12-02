"""
Email Validator Service
Validates email addresses for deliverability
"""

import re
import dns.resolver
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class EmailValidator:
    """Validates email addresses for syntax, domain, and deliverability"""
    
    # Common disposable email domains
    DISPOSABLE_DOMAINS = {
        'tempmail.com', 'throwaway.email', 'guerrillamail.com', 'mailinator.com',
        '10minutemail.com', 'temp-mail.org', 'fakeinbox.com', 'trashmail.com',
        'yopmail.com', 'tempail.com', 'mohmal.com', 'getnada.com'
    }
    
    # Common role-based prefixes
    ROLE_PREFIXES = {
        'admin', 'info', 'support', 'sales', 'contact', 'help', 'noreply',
        'no-reply', 'postmaster', 'webmaster', 'abuse', 'spam', 'marketing'
    }
    
    EMAIL_REGEX = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    def __init__(self):
        self.cache = {}
    
    def validate_syntax(self, email: str) -> Tuple[bool, str]:
        """Check if email has valid syntax"""
        if not email or not isinstance(email, str):
            return False, "Email is empty or invalid type"
        
        email = email.strip().lower()
        
        if len(email) > 254:
            return False, "Email too long"
        
        if not self.EMAIL_REGEX.match(email):
            return False, "Invalid email format"
        
        return True, "Valid syntax"
    
    def validate_domain(self, email: str) -> Tuple[bool, str]:
        """Check if domain has valid MX records"""
        try:
            domain = email.split('@')[1].lower()
            
            # Check cache first
            if domain in self.cache:
                return self.cache[domain]
            
            # Try MX records
            try:
                mx_records = dns.resolver.resolve(domain, 'MX')
                if mx_records:
                    self.cache[domain] = (True, "Valid MX records")
                    return True, "Valid MX records"
            except dns.resolver.NoAnswer:
                pass
            except dns.resolver.NXDOMAIN:
                self.cache[domain] = (False, "Domain does not exist")
                return False, "Domain does not exist"
            
            # Try A records as fallback
            try:
                a_records = dns.resolver.resolve(domain, 'A')
                if a_records:
                    self.cache[domain] = (True, "Valid A records (no MX)")
                    return True, "Valid A records (no MX)"
            except:
                pass
            
            self.cache[domain] = (False, "No MX or A records")
            return False, "No MX or A records"
            
        except Exception as e:
            logger.error(f"Domain validation error for {email}: {e}")
            return False, f"Domain validation error: {str(e)}"
    
    def is_disposable(self, email: str) -> bool:
        """Check if email uses a disposable domain"""
        try:
            domain = email.split('@')[1].lower()
            return domain in self.DISPOSABLE_DOMAINS
        except:
            return False
    
    def is_role_based(self, email: str) -> bool:
        """Check if email is role-based (info@, admin@, etc.)"""
        try:
            local_part = email.split('@')[0].lower()
            return local_part in self.ROLE_PREFIXES
        except:
            return False
    
    def validate(self, email: str) -> Dict:
        """Full validation of an email address"""
        result = {
            'email': email,
            'valid': False,
            'syntax_valid': False,
            'domain_valid': False,
            'is_disposable': False,
            'is_role_based': False,
            'reason': '',
            'score': 0
        }
        
        # Syntax check
        syntax_valid, syntax_msg = self.validate_syntax(email)
        result['syntax_valid'] = syntax_valid
        if not syntax_valid:
            result['reason'] = syntax_msg
            return result
        
        email = email.strip().lower()
        result['email'] = email
        
        # Domain check
        domain_valid, domain_msg = self.validate_domain(email)
        result['domain_valid'] = domain_valid
        if not domain_valid:
            result['reason'] = domain_msg
            return result
        
        # Disposable check
        result['is_disposable'] = self.is_disposable(email)
        
        # Role-based check
        result['is_role_based'] = self.is_role_based(email)
        
        # Calculate score
        score = 100
        if result['is_disposable']:
            score -= 50
        if result['is_role_based']:
            score -= 20
        
        result['score'] = score
        result['valid'] = True
        result['reason'] = 'Valid email'
        
        return result
    
    def validate_bulk(self, emails: List[str]) -> List[Dict]:
        """Validate multiple emails"""
        return [self.validate(email) for email in emails]


# Singleton instance
_validator = None

def get_validator() -> EmailValidator:
    """Get the singleton validator instance"""
    global _validator
    if _validator is None:
        _validator = EmailValidator()
    return _validator


def validate_email(email: str) -> Dict:
    """Convenience function to validate a single email"""
    return get_validator().validate(email)


def validate_emails(emails: List[str]) -> List[Dict]:
    """Convenience function to validate multiple emails"""
    return get_validator().validate_bulk(emails)
